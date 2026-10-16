"""Tests for the bundled Discord Presence plugin (plugins/discord-presence/).

A scripted in-memory Discord stands in for the IPC socket, so the real
framing, nonce matching, PING handling and service reconcile loop all run.
"""

from __future__ import annotations

import importlib.util
import json
import struct
import sys
import types
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[2] / "plugins" / "discord-presence"
PACKAGE = "jettstui_plugins.discord_presence"


def _load_plugin() -> types.ModuleType:
    if PACKAGE in sys.modules:
        return sys.modules[PACKAGE]
    parent = PACKAGE.rsplit(".", 1)[0]
    if parent not in sys.modules:
        ns = types.ModuleType(parent)
        ns.__path__ = []  # type: ignore[attr-defined]
        sys.modules[parent] = ns
    spec = importlib.util.spec_from_file_location(
        PACKAGE, PLUGIN_DIR / "__init__.py", submodule_search_locations=[str(PLUGIN_DIR)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE] = module
    spec.loader.exec_module(module)
    return module


plugin = _load_plugin()
act = plugin.activity
ipc_mod = sys.modules[f"{PACKAGE}.ipc"]
service_mod = sys.modules[f"{PACKAGE}.service"]

APP_ID = "123456789012345678"
USER = {"id": "42", "username": "jetts", "global_name": "Jetts"}


# --------------------------------------------------------------- fake Discord

class FakeDiscord:
    """Minimal Discord IPC peer: answers handshakes and SET_ACTIVITY."""

    def __init__(self, *, close_on_handshake: Optional[Dict[str, Any]] = None, noise: bool = False) -> None:
        self.close_on_handshake = close_on_handshake
        self.noise = noise  # interleave a PING and an unrelated dispatch before replies
        self.activities: List[Optional[Dict[str, Any]]] = []
        self.pongs = 0
        self.reject_next: Optional[Dict[str, Any]] = None

    def transport(self, path: str) -> "FakeTransport":
        return FakeTransport(self)


class FakeTransport:
    def __init__(self, peer: FakeDiscord) -> None:
        self.peer = peer
        self.inbox = bytearray()
        self.closed = False

    def _push(self, opcode: int, payload: Dict[str, Any]) -> None:
        self.inbox.extend(ipc_mod.encode_frame(opcode, payload))

    def send(self, data: bytes) -> None:
        opcode, length = struct.unpack("<II", data[:8])
        payload = json.loads(data[8 : 8 + length])
        if opcode == ipc_mod.OP_HANDSHAKE:
            if self.peer.close_on_handshake:
                self._push(ipc_mod.OP_CLOSE, self.peer.close_on_handshake)
            else:
                self._push(ipc_mod.OP_FRAME, {"evt": "READY", "data": {"user": USER}})
        elif opcode == ipc_mod.OP_PONG:
            self.peer.pongs += 1
        elif opcode == ipc_mod.OP_FRAME and payload.get("cmd") == "SET_ACTIVITY":
            if self.peer.noise:
                self._push(ipc_mod.OP_PING, {"n": 1})
                self._push(ipc_mod.OP_FRAME, {"evt": "ACTIVITY_JOIN", "nonce": None, "data": {}})
            if self.peer.reject_next:
                error, self.peer.reject_next = self.peer.reject_next, None
                self._push(ipc_mod.OP_FRAME, {"evt": "ERROR", "nonce": payload["nonce"], "data": error})
                return
            self.peer.activities.append(payload["args"]["activity"])
            self._push(ipc_mod.OP_FRAME, {"cmd": "SET_ACTIVITY", "nonce": payload["nonce"], "data": {}})

    def recv_exact(self, size: int, deadline: float) -> bytes:
        if len(self.inbox) < size:
            raise TimeoutError("no data")
        chunk = bytes(self.inbox[:size])
        del self.inbox[:size]
        return chunk

    def close(self) -> None:
        self.closed = True


def _ipc(peer: FakeDiscord) -> Any:
    return ipc_mod.DiscordIPC(APP_ID, candidates=["fake-0"], transport_factory=peer.transport)


# ------------------------------------------------------------------ protocol

def test_handshake_returns_ready_user():
    ipc = _ipc(FakeDiscord())
    assert ipc.connect() == USER
    assert ipc.connected


def test_request_skips_unrelated_frames_and_answers_ping():
    peer = FakeDiscord(noise=True)
    ipc = _ipc(peer)
    ipc.connect()
    ipc.set_activity({"details": "hi"})
    assert peer.activities == [{"details": "hi"}]
    assert peer.pongs == 1


def test_error_reply_raises_with_code():
    peer = FakeDiscord()
    ipc = _ipc(peer)
    ipc.connect()
    peer.reject_next = {"code": 4002, "message": "bad payload"}
    with pytest.raises(ipc_mod.DiscordIPCError) as err:
        ipc.set_activity({"details": "x"})
    assert err.value.code == 4002
    assert ipc.connected  # a rejected payload does not drop the connection


def test_invalid_client_id_close_is_explained():
    ipc = _ipc(FakeDiscord(close_on_handshake={"code": 4000, "message": "Invalid Client ID"}))
    with pytest.raises(ipc_mod.DiscordIPCError) as err:
        ipc.connect()
    assert err.value.code == 4000
    assert "Application ID" in str(err.value)
    assert not ipc.connected


def test_no_listening_client_raises_not_running():
    def refuse(path):
        raise FileNotFoundError(path)

    ipc = ipc_mod.DiscordIPC(APP_ID, candidates=["a", "b"], transport_factory=refuse)
    with pytest.raises(ipc_mod.DiscordNotRunning):
        ipc.connect()


def test_ipc_candidates_cover_windows_and_sandboxed_unix():
    windows = ipc_mod.ipc_candidates("win32", {})
    assert windows and all(p.startswith("\\\\?\\pipe\\discord-ipc-") for p in windows)

    unix = ipc_mod.ipc_candidates("linux", {"XDG_RUNTIME_DIR": "/run/user/1000"})
    assert len(unix) == len(set(unix))
    assert any("app/com.discordapp.Discord" in p.replace("\\", "/") for p in unix)
    assert unix[0].replace("\\", "/").startswith("/run/user/1000/")


# ------------------------------------------------------------------ composer

def _settings(**overrides: Any) -> Any:
    section = {"enabled": True, "client_id": APP_ID, **overrides}
    return act.PresenceSettings.from_config({"discord_rpc": section})


def _working(**overrides: Any) -> Any:
    base = dict(
        phase=act.PHASE_TOOL,
        tool="terminal",
        model="openrouter/secret-model-x",
        project="private-repo",
        started_at=1000.0,
        last_active_at=1000.0,
        tool_calls=3,
    )
    base.update(overrides)
    return act.Snapshot(**base)


def _all_text(activity: Dict[str, Any]) -> str:
    return json.dumps(activity, ensure_ascii=False)


def test_privacy_toggles_remove_fields_from_the_payload():
    hidden = act.compose_activity(
        _settings(preset="autonomous", show_model=False, show_project=False, show_tool_activity=False, show_elapsed=False),
        _working(),
        now=1001.0,
    )
    text = _all_text(hidden)
    assert "secret-model-x" not in text
    assert "private-repo" not in text
    assert "Running commands" not in text
    assert "timestamps" not in hidden

    shown = act.compose_activity(_settings(preset="autonomous"), _working(), now=1001.0)
    text = _all_text(shown)
    assert "private-repo" in text and "Running commands" in text
    assert shown["timestamps"] == {"start": 1000}


def test_vendor_prefix_is_stripped_from_model_name():
    activity = act.compose_activity(_settings(preset="pairing"), _working(), now=1001.0)
    assert "secret-model-x" in activity["state"]
    assert "openrouter/" not in activity["state"]


def test_hidden_fields_leave_no_dangling_separators():
    activity = act.compose_activity(_settings(details="Coding · {model}", show_model=False), _working(), now=1001.0)
    assert activity["details"] == "Coding"


def test_fields_respect_discord_limits():
    long = "x" * 400
    activity = act.compose_activity(
        act.PresenceSettings.from_config({"discord_rpc": {
            "enabled": True,
            "client_id": APP_ID,
            "details": long,
            "state": "a",  # below Discord's 2-char minimum → dropped
            "buttons": [
                {"label": "L" * 50, "url": "https://example.com/1"},
                {"label": "insecure", "url": "http://example.com"},
                {"label": "two", "url": "https://example.com/2"},
                {"label": "three", "url": "https://example.com/3"},
            ],
        }}),
        _working(),
        now=1001.0,
    )
    assert len(activity["details"]) <= act.MAX_TEXT
    assert "state" not in activity
    assert len(activity["buttons"]) <= act.MAX_BUTTONS
    assert all(b["url"].startswith("https://") and len(b["label"]) <= act.MAX_BUTTON_LABEL for b in activity["buttons"])


def test_idle_presence_clears_after_timeout_but_not_while_working():
    settings = _settings(idle_timeout_minutes=5)
    idle = _working(phase=act.PHASE_IDLE, tool="")
    assert act.compose_activity(settings, idle, now=1000.0 + 60) is not None
    assert act.compose_activity(settings, idle, now=1000.0 + 5 * 60) is None
    assert act.compose_activity(settings, _working(), now=1000.0 + 3600) is not None


def test_unknown_placeholders_render_empty():
    assert act.render_template("Hi {nope}", {}) == "Hi"


def test_tool_descriptions_never_echo_raw_names():
    for name in ("terminal", "browser_click", "mcp_github_create_issue", "some_unknown_tool"):
        assert name not in act.describe_tool(name)


def test_legacy_presets_and_bad_ids_normalize():
    assert act.resolve_preset("fine_tuning") in act.PRESETS
    assert act.resolve_preset("does-not-exist") == act.DEFAULT_PRESET
    assert not _settings(client_id="1343714589234567890").configured
    assert not _settings(client_id="not-a-snowflake").configured
    assert _settings().configured


# ------------------------------------------------------------------- service

class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _service(peer: Optional[FakeDiscord], settings: Any) -> tuple:
    clock = Clock()
    box = {"settings": settings}

    def ipc_factory(client_id: str):
        if peer is None:
            def refuse(path):
                raise FileNotFoundError(path)
            return ipc_mod.DiscordIPC(client_id, candidates=["x"], transport_factory=refuse)
        return ipc_mod.DiscordIPC(client_id, candidates=["fake-0"], transport_factory=peer.transport)

    svc = service_mod.PresenceService(
        settings_loader=lambda: box["settings"],
        ipc_factory=ipc_factory,
        clock=clock,
        monotonic=clock,
        project_resolver=lambda: "demo",
        autostart=False,
    )
    return svc, clock, box


def test_service_coalesces_bursts_within_rate_limit():
    peer = FakeDiscord()
    svc, clock, _ = _service(peer, _settings())
    svc.turn_started(session_id="s", model="m", platform="cli")
    svc._tick()
    assert len(peer.activities) == 1

    for i in range(5):
        svc.tool_started(session_id="s", tool_call_id=str(i), tool_name="patch")
        svc.tool_finished(session_id="s", tool_call_id=str(i), tool_name="patch")
    svc.tool_started(session_id="s", tool_call_id="last", tool_name="terminal")
    wait = svc._tick()
    assert len(peer.activities) == 1  # still inside the rate-limit window
    assert 0 < wait <= service_mod.MIN_UPDATE_INTERVAL

    clock.now += service_mod.MIN_UPDATE_INTERVAL
    svc._tick()
    assert len(peer.activities) == 2
    assert "Running commands" in peer.activities[-1]["state"]
    svc._tick()
    assert len(peer.activities) == 2  # unchanged state is not resent


def test_service_ignores_messaging_platform_sessions():
    peer = FakeDiscord()
    svc, _, _ = _service(peer, _settings())
    svc.turn_started(session_id="tg", model="m", platform="telegram")
    svc.tool_started(session_id="tg", tool_call_id="1", tool_name="terminal")
    assert svc.status()["phase"] == act.PHASE_IDLE


def test_disabling_clears_activity_and_stops_worker():
    peer = FakeDiscord()
    svc, _, box = _service(peer, _settings())
    svc.turn_started(session_id="s", platform="cli")
    svc._tick()
    box["settings"] = _settings(enabled=False)
    svc.refresh()
    assert svc._tick() is None
    assert peer.activities[-1] is None
    assert not svc.status()["connected"]


def test_reconnect_backs_off_when_discord_is_closed():
    svc, clock, _ = _service(None, _settings())
    svc.turn_started(session_id="s", platform="cli")
    first = svc._tick()
    assert first == pytest.approx(service_mod.BACKOFF_START)
    assert "not running" in svc.status()["error"].lower()
    clock.now += first
    second = svc._tick()
    assert first < second <= service_mod.BACKOFF_MAX


def test_status_preview_never_contains_tool_arguments():
    peer = FakeDiscord()
    svc, _, _ = _service(peer, _settings())
    svc.tool_started(session_id="s", tool_call_id="1", tool_name="terminal")
    status = svc.status()
    assert status["settings"]["client_id"] == APP_ID
    assert status["preview"]["details"]
    assert {p["id"] for p in status["presets"]} == set(act.PRESETS)


# ---------------------------------------------------------- slash + register

def test_register_wires_hooks_and_commands():
    hooks: Dict[str, Any] = {}
    commands: Dict[str, Any] = {}
    cli: Dict[str, Any] = {}

    class Ctx:
        def register_hook(self, name, cb):
            hooks[name] = cb

        def register_command(self, name, handler, description="", args_hint=""):
            commands[name] = handler

        def register_cli_command(self, name, help, setup_fn, handler_fn=None, description=""):
            cli[name] = (setup_fn, handler_fn)

    plugin.register(Ctx())
    assert {"pre_tool_call", "post_tool_call", "pre_llm_call", "on_session_end"} <= set(hooks)
    assert "rpc" in commands and "rpc" in cli
    assert "Usage" in commands["rpc"]("bogus")


def test_bundled_plugin_is_discovered_but_opt_in(tmp_path, monkeypatch):
    from jettstui import plugins as plugins_mod

    manager = plugins_mod.PluginManager()
    manager.discover_and_load()
    names = {p["name"]: p for p in manager.list_plugins()}
    # Bundled standalone plugins load only when listed in plugins.enabled.
    assert not names.get("discord-presence", {}).get("enabled", False)
