"""The TUI child must see the same JETTSTUI_HOME the backend resolved.

Its own fallback is ~/.jettstui, which on Windows is not the home
(%LOCALAPPDATA%\jettstui), so its boot-theme cache landed elsewhere and every
launch repainted from the built-in palette.
"""

import pytest

import jettstui.main as main_mod


def _run_launch(monkeypatch, tmp_path):
    captured = {}

    def fake_call(argv, cwd=None, env=None):
        captured["env"] = env
        return 1

    monkeypatch.setattr(main_mod, "_make_tui_argv", lambda tui_dir, tui_dev: (["node"], tmp_path))
    monkeypatch.setattr(main_mod.subprocess, "call", fake_call)
    with pytest.raises(SystemExit):
        main_mod._launch_tui()
    return captured["env"]


def test_tui_gets_the_resolved_home_when_unset_or_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("JETTSTUI_HOME", "")
    monkeypatch.setattr(main_mod, "get_jettstui_home", lambda: tmp_path / "home")

    env = _run_launch(monkeypatch, tmp_path)

    assert env["JETTSTUI_HOME"] == str(tmp_path / "home")


def test_tui_keeps_an_explicit_home(monkeypatch, tmp_path):
    profile = str(tmp_path / "profiles" / "coder")
    monkeypatch.setenv("JETTSTUI_HOME", profile)

    env = _run_launch(monkeypatch, tmp_path)

    assert env["JETTSTUI_HOME"] == profile
