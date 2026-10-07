"""Layout and interaction contracts for the Studio terminal presentation."""

from io import StringIO

import pytest
from rich.cells import cell_len
from rich.console import Console

from freeide_cli.skin_engine import load_skin
from freeide_cli.studio import activity_line, composer_hint, welcome_panel


@pytest.mark.parametrize("width", [20, 32, 53, 54, 80, 120])
def test_welcome_fits_terminal_and_keeps_user_text_literal(width):
    stream = StringIO()
    console = Console(file=stream, width=width, color_system=None)
    console.print(welcome_panel(
        skin=load_skin("studio"), width=width,
        model="[red]model[/red]", provider="openrouter", cwd="C:/work/项目/[demo]",
        tools=12, skills=4, context=128000, session="session-123",
    ))
    output = stream.getvalue()
    assert all(cell_len(line) <= width for line in output.splitlines())
    if width >= 54:
        assert "Jetts-TUI" in output
        assert "FreeIDE" not in output
        assert "[red]model[/red]" in output
        assert "/resume" in output
        assert "[demo]" in output


@pytest.mark.parametrize("width", [1, 8, 24, 40, 80])
def test_activity_never_wraps_even_with_wide_characters(width):
    row = activity_line("Reading 项目/文件.py " * 12, width=width, now=1.2,
                        elapsed=123, tokens="1.2k tokens")
    assert cell_len(row) < width


def test_reduced_motion_preserves_status_without_changing_frame():
    kwargs = dict(label="· thinking...", width=80, reduce_motion=True)
    assert activity_line(now=0, **kwargs) == activity_line(now=1, **kwargs)
    assert "thinking" in activity_line(now=0, **kwargs)
    assert activity_line("Reading", width=80, now=0) != activity_line("Reading", width=80, now=.12)


@pytest.mark.parametrize(("mode", "action"), [
    ("interrupt", "redirect"), ("queue", "queue"), ("steer", "guide"),
])
def test_busy_hint_describes_configured_enter_behavior(mode, action):
    hint = composer_hint(busy=True, mode=mode)
    assert action in hint
    assert "Ctrl+C" in hint


def test_studio_integration_uses_active_profile_config(tmp_path, monkeypatch):
    monkeypatch.setenv("FREEIDE_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text("display:\n  skin: studio\n", encoding="utf-8")
    from freeide_cli.config import load_config
    from freeide_cli.skin_engine import init_skin_from_config, get_active_skin_name, set_active_skin
    previous = get_active_skin_name()
    try:
        init_skin_from_config(load_config())
        assert get_active_skin_name() == "studio"
    finally:
        set_active_skin(previous)


def test_cli_activity_widget_stays_on_one_row(monkeypatch):
    from cli import FreeIDECLI
    from freeide_cli.skin_engine import get_active_skin_name, set_active_skin
    shell = FreeIDECLI.__new__(FreeIDECLI)
    shell._spinner_text = "Reading 项目/file.py " * 20
    shell._spinner_token_flow_enabled = False
    shell._tool_start_time = 0
    monkeypatch.setattr(shell, "_get_tui_terminal_width", lambda: 80)
    previous = get_active_skin_name()
    try:
        set_active_skin("studio")
        assert shell._spinner_widget_height() == 1
        assert "Reading" in shell._render_spinner_text()
    finally:
        set_active_skin(previous)
