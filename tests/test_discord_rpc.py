"""Unit tests for the Discord Rich Presence (RPC) module."""

from __future__ import annotations

import asyncio
import json
import os
import platform
import struct
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jettstui.discord_rpc import (
    DEFAULT_CLIENT_ID,
    MAX_BUTTON_LABEL_LEN,
    MAX_DETAILS_LEN,
    MAX_STATE_LEN,
    OP_CLOSE,
    OP_FRAME,
    OP_HANDSHAKE,
    PRESETS,
    ActivityAssets,
    ActivityButton,
    DiscordIPCClient,
    DiscordRPCManager,
    RichPresence,
    find_active_ipc_pipe,
    format_template,
    get_ipc_pipe_candidates,
    render_discord_card,
)


class TestDiscordRPCProtocol:
    """Test low-level protocol encoding, packing, and validation."""

    def test_opcodes_match_discord_specification(self):
        assert OP_HANDSHAKE == 0
        assert OP_FRAME == 1
        assert OP_CLOSE == 2

    def test_packet_framing_header(self):
        payload = {"v": 1, "client_id": "123456789"}
        payload_bytes = json.dumps(payload).encode("utf-8")
        header = struct.pack("<II", OP_HANDSHAKE, len(payload_bytes))
        assert len(header) == 8

        op, length = struct.unpack("<II", header)
        assert op == OP_HANDSHAKE
        assert length == len(payload_bytes)

    def test_pipe_candidates_include_standard_paths(self):
        candidates = get_ipc_pipe_candidates()
        assert len(candidates) > 0
        system = platform.system().lower()
        if system == "windows":
            assert any(r"\\.\pipe\discord-ipc-0" in c for c in candidates)
        elif system == "darwin":
            assert any("discord-ipc-0" in c for c in candidates)
        else:
            assert any("discord-ipc-0" in c for c in candidates)


class TestRichPresencePayload:
    """Test payload building, truncation, and sanitization."""

    def test_empty_presence_prunes_none(self):
        presence = RichPresence()
        d = presence.to_payload_dict()
        assert d == {"instance": True}

    def test_truncates_oversized_details_and_state(self):
        oversized = "A" * 200
        presence = RichPresence(details=oversized, state=oversized)
        d = presence.to_payload_dict()
        assert len(d["details"]) == MAX_DETAILS_LEN
        assert len(d["state"]) == MAX_STATE_LEN

    def test_timestamps_integer_conversion(self):
        presence = RichPresence(start_time=1700000000.75, end_time=1700003600.25)
        d = presence.to_payload_dict()
        assert d["timestamps"]["start"] == 1700000000
        assert d["timestamps"]["end"] == 1700003600

    def test_buttons_clamped_to_max_two_and_truncated(self):
        buttons = [
            ActivityButton("A" * 50, "https://github.com/one"),
            ActivityButton("B" * 50, "https://github.com/two"),
            ActivityButton("C" * 50, "https://github.com/three"),
        ]
        presence = RichPresence(buttons=buttons)
        d = presence.to_payload_dict()
        assert len(d["buttons"]) == 2
        assert len(d["buttons"][0]["label"]) == MAX_BUTTON_LABEL_LEN
        assert d["buttons"][0]["url"] == "https://github.com/one"
        assert d["buttons"][1]["url"] == "https://github.com/two"

    def test_assets_dict_omits_none(self):
        assets = ActivityAssets(
            large_image="https://example.com/logo.png",
            large_text="Custom Logo",
            small_image=None,
            small_text=None,
        )
        presence = RichPresence(assets=assets)
        d = presence.to_payload_dict()
        assert "large_image" in d["assets"]
        assert "large_text" in d["assets"]
        assert "small_image" not in d["assets"]
        assert "small_text" not in d["assets"]


class TestPresetsAndFormatting:
    """Test template substitution and preset configurations."""

    def test_presets_exist_and_have_required_fields(self):
        assert "pairing" in PRESETS
        assert "vibe_coding" in PRESETS
        assert "autonomous" in PRESETS
        assert "fine_tuning" in PRESETS
        assert "idle" in PRESETS

        for name, preset in PRESETS.items():
            assert "details" in preset
            assert "state" in preset
            assert "name" in preset

    def test_template_substitution(self):
        tpl = "Pairing with {model} on {project}"
        ctx = {"model": "Qwen2.5-Coder-32B", "project": "JETTS-TUI"}
        out = format_template(tpl, ctx)
        assert out == "Pairing with Qwen2.5-Coder-32B on JETTS-TUI"

    def test_template_handles_missing_keys_gracefully(self):
        tpl = "Testing {model} with {unknown_variable}"
        ctx = {"model": "Claude"}
        out = format_template(tpl, ctx)
        # Should not raise exception
        assert isinstance(out, str)


class TestDiscordRPCManager:
    """Test DiscordRPCManager state tracking and lifecycle."""

    def test_manager_builds_current_presence(self):
        mgr = DiscordRPCManager(
            preset="pairing",
            enabled=False,
        )
        mgr.on_session_start(model="Qwen2.5-Coder", project="MyRepo")
        presence = mgr.build_current_presence()
        payload = presence.to_payload_dict()

        assert "Qwen2.5-Coder" in payload["details"]
        assert "MyRepo" in payload["state"]
        assert len(payload["buttons"]) == 2

    def test_tool_start_and_end_updates_details(self):
        mgr = DiscordRPCManager(preset="pairing", enabled=False)
        mgr.on_session_start(model="Qwen2.5-Coder", project="MyRepo")

        mgr.on_tool_start("search_files")
        presence = mgr.build_current_presence()
        assert "Running: search_files" in presence.details

        mgr.on_tool_end("search_files")
        presence = mgr.build_current_presence()
        assert "search_files" not in (presence.details or "")

    def test_set_custom_overrides_preset(self):
        mgr = DiscordRPCManager(preset="pairing", enabled=False)
        mgr.set_custom(state="Custom State 123", details="Custom Details 456")
        presence = mgr.build_current_presence()
        assert presence.state == "Custom State 123"
        assert presence.details == "Custom Details 456"

    def test_switch_preset(self):
        mgr = DiscordRPCManager(preset="pairing", enabled=False)
        assert mgr.set_preset("vibe_coding") is True
        assert mgr.preset == "vibe_coding"
        assert mgr.set_preset("invalid_nonexistent") is False


class TestDiscordClientAsync:
    """Test DiscordIPCClient async handshake and operations using mocks."""

    @pytest.mark.asyncio
    async def test_handshake_and_set_activity(self):
        client = DiscordIPCClient(client_id=DEFAULT_CLIENT_ID)
        mock_reader = AsyncMock()
        mock_writer = MagicMock()
        mock_writer.drain = AsyncMock()
        mock_writer.wait_closed = AsyncMock()

        client.reader = mock_reader
        client.writer = mock_writer

        # Handshake response: 8-byte preamble + json
        handshake_resp = {"cmd": "DISPATCH", "evt": "READY", "data": {"v": 1}}
        resp_bytes = json.dumps(handshake_resp).encode("utf-8")
        preamble = struct.pack("<II", OP_FRAME, len(resp_bytes))

        # First read preamble, second read payload
        mock_reader.readexactly = AsyncMock(side_effect=[preamble, resp_bytes])

        # Manually invoke handshake verification
        handshake_payload = {"v": 1, "client_id": client.client_id}
        await client._send_packet(OP_HANDSHAKE, handshake_payload)
        op, response = await client._read_packet()

        assert op == OP_FRAME
        assert response["evt"] == "READY"
        client.is_connected = True

        # Now test set_activity response
        act_resp = {"cmd": "SET_ACTIVITY", "evt": None, "data": {}}
        act_bytes = json.dumps(act_resp).encode("utf-8")
        act_preamble = struct.pack("<II", OP_FRAME, len(act_bytes))
        mock_reader.readexactly = AsyncMock(side_effect=[act_preamble, act_bytes])

        presence = RichPresence(state="Coding", details="JettsTUI")
        ok = await client.set_activity(presence)
        assert ok is True

        await client.close()
        assert client.is_connected is False


class TestDiscordCardRenderer:
    """Test terminal profile card rendering."""

    def test_renders_card_without_error(self):
        presence = RichPresence(
            state="📂 Workspace: JETTS-TUI",
            details="⚡ Pairing with JettsTUI",
            start_time=1700000000,
            assets=ActivityAssets(),
            buttons=[ActivityButton("⭐ Star on GitHub", "https://github.com/Raioshok/JETTS-TUI")],
        )
        card = render_discord_card(presence, client_name="JettsTUI", is_connected=True)
        assert card is not None
        # String conversion works
        card_str = str(card)
        assert "JETTS-TUI" in card_str or hasattr(card, "__rich_console__")
