"""Tests for banner toolset name normalization and skin color usage."""

from unittest.mock import patch

import pytest
from rich.console import Console

import freeide_cli.banner as banner
import model_tools
import tools.mcp_tool


@pytest.fixture(autouse=True)
def use_standard_banner():
    """The user's selected skin must not change these banner contracts."""
    with patch("freeide_cli.skin_engine.get_active_skin", return_value=None):
        yield


def test_display_toolset_name_strips_legacy_suffix():
    assert banner._display_toolset_name("homeassistant_tools") == "homeassistant"
    assert banner._display_toolset_name("honcho_tools") == "honcho"
    assert banner._display_toolset_name("web_tools") == "web"


def test_display_toolset_name_preserves_clean_names():
    assert banner._display_toolset_name("browser") == "browser"
    assert banner._display_toolset_name("file") == "file"
    assert banner._display_toolset_name("terminal") == "terminal"


def test_display_toolset_name_handles_empty():
    assert banner._display_toolset_name("") == "unknown"
    assert banner._display_toolset_name(None) == "unknown"


def test_build_welcome_banner_uses_normalized_toolset_names():
    """Unavailable toolsets should not have '_tools' appended in banner output."""
    with (
        patch.object(
            model_tools,
            "check_tool_availability",
            return_value=(
                ["web"],
                [
                    {"name": "homeassistant", "tools": ["ha_call_service"]},
                    {"name": "honcho", "tools": ["honcho_conclude"]},
                ],
            ),
        ),
        patch.object(banner, "get_available_skills", return_value={}),
        patch.object(banner, "get_update_result", return_value=None),
        patch.object(tools.mcp_tool, "get_mcp_status", return_value=[]),
    ):
        console = Console(
            record=True, force_terminal=False, color_system=None, width=160
        )
        banner.build_welcome_banner(
            console=console,
            model="anthropic/test-model",
            cwd="/tmp/project",
            tools=[
                {"function": {"name": "web_search"}},
                {"function": {"name": "read_file"}},
            ],
            get_toolset_for_tool=lambda name: {
                "web_search": "web_tools",
                "read_file": "file",
            }.get(name),
        )

    output = console.export_text()
    assert "homeassistant" in output
    assert "honcho" in output
    assert "web" in output
    assert "homeassistant_tools" not in output
    assert "honcho_tools" not in output
    assert "web_tools" not in output


def test_build_welcome_banner_title_is_hyperlinked_to_release():
    """Panel title (version label) is wrapped in an OSC-8 hyperlink to the GitHub release."""
    import io
    from unittest.mock import patch as _patch
    import freeide_cli.banner as _banner
    import model_tools as _mt
    import tools.mcp_tool as _mcp

    _banner._latest_release_cache = None
    tag_url = ("v2026.4.23", "https://github.com/Raioshok/JETTS-TUI/releases/tag/v2026.4.23")

    buf = io.StringIO()
    with (
        _patch.object(_mt, "check_tool_availability", return_value=(["web"], [])),
        _patch.object(_banner, "get_available_skills", return_value={}),
        _patch.object(_banner, "get_update_result", return_value=None),
        _patch.object(_mcp, "get_mcp_status", return_value=[]),
        _patch.object(_banner, "get_latest_release_tag", return_value=tag_url),
    ):
        console = Console(file=buf, force_terminal=True, color_system="truecolor", legacy_windows=False, width=160)
        _banner.build_welcome_banner(
            console=console, model="x", cwd="/tmp",
            session_id="abc123",
            tools=[{"function": {"name": "read_file"}}],
            get_toolset_for_tool=lambda n: "file",
        )

    raw = buf.getvalue()
    # The existing version label must still be present in the title
    assert "Jetts-TUI v" in raw, "Version label missing from title"
    # OSC-8 hyperlink escape sequence present with the release URL
    assert "\x1b]8;" in raw, "OSC-8 hyperlink not emitted"
    assert "releases/tag/v2026.4.23" in raw, "Release URL missing from banner output"


def test_build_welcome_banner_title_falls_back_when_no_tag():
    """Without a resolvable tag, the panel title renders as plain text (no hyperlink escape)."""
    import io
    from unittest.mock import patch as _patch
    import freeide_cli.banner as _banner
    import model_tools as _mt
    import tools.mcp_tool as _mcp

    _banner._latest_release_cache = None
    buf = io.StringIO()
    with (
        _patch.object(_mt, "check_tool_availability", return_value=(["web"], [])),
        _patch.object(_banner, "get_available_skills", return_value={}),
        _patch.object(_banner, "get_update_result", return_value=None),
        _patch.object(_mcp, "get_mcp_status", return_value=[]),
        _patch.object(_banner, "get_latest_release_tag", return_value=None),
    ):
        console = Console(file=buf, force_terminal=True, color_system="truecolor", legacy_windows=False, width=160)
        _banner.build_welcome_banner(
            console=console, model="x", cwd="/tmp",
            session_id="abc123",
            tools=[{"function": {"name": "read_file"}}],
            get_toolset_for_tool=lambda n: "file",
        )

    raw = buf.getvalue()
    assert "Jetts-TUI v" in raw, "Version label missing from title"
    assert "\x1b]8;" not in raw, "OSC-8 hyperlink should not be emitted without a tag"


def test_build_welcome_banner_does_not_count_disconnected_mcp():
    """The compact banner counts connected MCP servers only."""
    with (
        patch.object(model_tools, "check_tool_availability", return_value=(["web"], [])),
        patch.object(banner, "get_available_skills", return_value={}),
        patch.object(banner, "get_update_result", return_value=None),
        patch.object(
            tools.mcp_tool,
            "get_mcp_status",
            return_value=[
                {"name": "linear", "transport": "http", "tools": 0,
                 "connected": False, "disabled": True},
                {"name": "broken", "transport": "stdio", "tools": 0,
                 "connected": False, "disabled": False},
            ],
        ),
    ):
        console = Console(record=True, force_terminal=False, color_system=None, width=160)
        banner.build_welcome_banner(
            console=console, model="anthropic/test-model", cwd="/tmp/project",
            tools=[{"function": {"name": "read_file"}}],
            get_toolset_for_tool=lambda n: "file",
        )

    output = console.export_text()
    assert "MCP" not in output
    assert "linear" not in output
    assert "broken" not in output


def test_build_welcome_banner_configured_mcp_is_not_counted():
    """A configured but disconnected MCP server is not advertised as connected."""
    with (
        patch.object(model_tools, "check_tool_availability", return_value=(["web"], [])),
        patch.object(banner, "get_available_skills", return_value={}),
        patch.object(banner, "get_update_result", return_value=None),
        patch.object(
            tools.mcp_tool,
            "get_mcp_status",
            return_value=[
                {
                    "name": "docker-profile",
                    "transport": "stdio",
                    "tools": 0,
                    "connected": False,
                    "disabled": False,
                    "status": "configured",
                },
            ],
        ),
    ):
        console = Console(record=True, force_terminal=False, color_system=None, width=160)
        banner.build_welcome_banner(
            console=console, model="anthropic/test-model", cwd="/tmp/project",
            tools=[{"function": {"name": "read_file"}}],
            get_toolset_for_tool=lambda n: "file",
        )

    output = console.export_text()
    assert "MCP" not in output
    assert "docker-profile" not in output
    assert "failed" not in output


def test_banner_hides_toolsets_not_enabled_for_platform():
    """A globally-registered toolset that isn't enabled for this agent (e.g.
    discord / feishu on a CLI session) must NOT appear in 'Available Tools'.

    Regression: check_tool_availability() walks the global registry, so the
    banner used to merge in every unavailable toolset regardless of whether it
    was part of this platform's set. On a Blank Slate CLI (file + terminal only)
    that surfaced discord/feishu tools the agent was never given.
    """
    with (
        patch.object(
            model_tools,
            "check_tool_availability",
            return_value=(
                ["file", "terminal"],
                [
                    {"name": "discord", "tools": ["discord_fetch_messages"]},
                    {"name": "feishu_doc", "tools": ["feishu_doc_read"]},
                ],
            ),
        ),
        patch.object(banner, "get_available_skills", return_value={}),
        patch.object(banner, "get_update_result", return_value=None),
        patch.object(tools.mcp_tool, "get_mcp_status", return_value=[]),
    ):
        console = Console(record=True, force_terminal=False, color_system=None, width=160)
        banner.build_welcome_banner(
            console=console,
            model="anthropic/test-model",
            cwd="/tmp/project",
            tools=[{"function": {"name": "read_file"}}],
            enabled_toolsets=["file", "terminal"],
            get_toolset_for_tool=lambda n: "file",
        )

    output = console.export_text()
    assert "discord" not in output
    assert "feishu" not in output


def test_banner_skills_section_reflects_disabled_skills_toolset():
    """The compact count excludes on-disk skills when that toolset is disabled."""
    fake_skills = {"creative": ["ascii-art", "p5js"], "devops": ["bug-triage-work"]}

    # Skills toolset disabled: no catalog count is advertised.
    with (
        patch.object(model_tools, "check_tool_availability", return_value=(["file", "terminal"], [])),
        patch.object(banner, "get_available_skills", return_value=fake_skills),
        patch.object(banner, "get_update_result", return_value=None),
        patch.object(tools.mcp_tool, "get_mcp_status", return_value=[]),
    ):
        console = Console(record=True, force_terminal=False, color_system=None, width=160)
        banner.build_welcome_banner(
            console=console, model="m", cwd="/tmp", tools=[{"function": {"name": "read_file"}}],
            enabled_toolsets=["file", "terminal"], get_toolset_for_tool=lambda n: "file",
        )
    out_disabled = console.export_text()
    assert "0 skills" in out_disabled
    assert "ascii-art" not in out_disabled

    # Skills toolset enabled: count the available catalog without a name wall.
    with (
        patch.object(model_tools, "check_tool_availability", return_value=(["file", "terminal", "skills"], [])),
        patch.object(banner, "get_available_skills", return_value=fake_skills),
        patch.object(banner, "get_update_result", return_value=None),
        patch.object(tools.mcp_tool, "get_mcp_status", return_value=[]),
    ):
        console = Console(record=True, force_terminal=False, color_system=None, width=160)
        banner.build_welcome_banner(
            console=console, model="m", cwd="/tmp", tools=[{"function": {"name": "read_file"}}],
            enabled_toolsets=["file", "terminal", "skills"], get_toolset_for_tool=lambda n: "file",
        )
    out_enabled = console.export_text()
    assert "3 skills" in out_enabled
    assert "ascii-art" not in out_enabled


def test_build_welcome_banner_moa_provider_shows_preset_and_aggregator(tmp_path, monkeypatch):
    """With provider='moa', the banner renders the preset + aggregator, not a bare slug."""
    import yaml

    home = tmp_path / ".freeide"
    home.mkdir()
    monkeypatch.setenv("FREEIDE_HOME", str(home))
    (home / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "moa": {
                    "default_preset": "opus-gpt",
                    "presets": {
                        "opus-gpt": {
                            "enabled": True,
                            "reference_models": [
                                {"provider": "openrouter", "model": "openai/gpt-5.5"},
                                {"provider": "openrouter", "model": "anthropic/claude-opus-4.8"},
                            ],
                            "aggregator": {"provider": "openrouter", "model": "anthropic/claude-opus-4.8"},
                        }
                    },
                }
            }
        )
    )

    with (
        patch.object(model_tools, "check_tool_availability", return_value=([], [])),
        patch.object(banner, "get_available_skills", return_value={}),
        patch.object(banner, "get_update_result", return_value=None),
        patch.object(tools.mcp_tool, "get_mcp_status", return_value=[]),
    ):
        console = Console(record=True, force_terminal=False, color_system=None, width=160)
        banner.build_welcome_banner(
            console=console,
            model="opus-gpt",
            cwd="/tmp/project",
            tools=[],
            enabled_toolsets=[],
            provider="moa",
        )

    out = console.export_text()
    assert "opus-gpt" in out
    assert "MoA" in out


def test_build_welcome_banner_non_moa_unchanged(tmp_path, monkeypatch):
    """A normal provider still renders the bare model slug, no MoA prefix."""
    monkeypatch.setenv("FREEIDE_HOME", str(tmp_path / ".freeide"))
    (tmp_path / ".freeide").mkdir()

    with (
        patch.object(model_tools, "check_tool_availability", return_value=([], [])),
        patch.object(banner, "get_available_skills", return_value={}),
        patch.object(banner, "get_update_result", return_value=None),
        patch.object(tools.mcp_tool, "get_mcp_status", return_value=[]),
    ):
        console = Console(record=True, force_terminal=False, color_system=None, width=160)
        banner.build_welcome_banner(
            console=console,
            model="anthropic/claude-opus-4.8",
            cwd="/tmp/project",
            tools=[],
            enabled_toolsets=[],
            provider="openrouter",
        )

    out = console.export_text()
    assert "claude-opus-4.8" in out
    assert "MoA:" not in out
