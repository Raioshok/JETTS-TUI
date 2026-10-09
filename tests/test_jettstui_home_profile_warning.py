"""Tests for get_jettstui_home() profile-mode fallback warning.

Regression test for https://github.com/Raioshok/JETTS-TUI/issues/18594.

When JETTSTUI_HOME is unset but an active_profile file indicates a non-default
profile is active, get_jettstui_home() should:
  1. STILL return ~/.jettstui (raising would brick 30+ module-level callers)
  2. Emit a loud one-shot warning to stderr so operators can diagnose
     cross-profile data contamination after the fact.

The warning goes to stderr directly (not through logging) because this
function is called at module-import time from 30+ sites, often before the
logging subsystem has been configured.
"""

from pathlib import Path
import sys

import pytest


@pytest.fixture
def fresh_constants(monkeypatch, tmp_path):
    """Import jettstui_constants fresh and reset the one-shot warn flag."""
    import importlib
    import jettstui_constants
    importlib.reload(jettstui_constants)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("JETTSTUI_HOME", raising=False)
    return jettstui_constants


def _default_home(tmp_path: Path) -> Path:
    return tmp_path / ("jettstui" if sys.platform == "win32" else ".jettstui")


class TestGetJettsTUIHomeProfileWarning:
    def test_classic_mode_no_active_profile_no_warning(
        self, fresh_constants, tmp_path, capsys
    ):
        """Classic mode: no active_profile file → silent, returns ~/.jettstui."""
        result = fresh_constants.get_jettstui_home()
        assert result == _default_home(tmp_path)
        assert "JETTSTUI_HOME fallback" not in capsys.readouterr().err

    def test_default_active_profile_no_warning(
        self, fresh_constants, tmp_path, capsys
    ):
        """active_profile=default → still no warning, returns ~/.jettstui."""
        jettstui_dir = _default_home(tmp_path)
        jettstui_dir.mkdir()
        (jettstui_dir / "active_profile").write_text("default\n")
        result = fresh_constants.get_jettstui_home()
        assert result == _default_home(tmp_path)
        assert "JETTSTUI_HOME fallback" not in capsys.readouterr().err

    def test_named_profile_unset_home_warns_once(
        self, fresh_constants, tmp_path, capsys
    ):
        """active_profile=coder + JETTSTUI_HOME unset → warn loudly, still return fallback."""
        jettstui_dir = _default_home(tmp_path)
        jettstui_dir.mkdir()
        (jettstui_dir / "active_profile").write_text("coder\n")

        result = fresh_constants.get_jettstui_home()

        # 1. Still returns the fallback — no import-time crash
        assert result == _default_home(tmp_path)
        # 2. Stderr got the warning exactly once
        err = capsys.readouterr().err
        assert err.count("JETTSTUI_HOME fallback") == 1
        assert "'coder'" in err
        assert "#18594" in err

        # 3. One-shot: second and third calls don't re-warn
        fresh_constants.get_jettstui_home()
        fresh_constants.get_jettstui_home()
        err2 = capsys.readouterr().err
        assert "JETTSTUI_HOME fallback" not in err2

    def test_jettstui_home_set_suppresses_warning(
        self, fresh_constants, tmp_path, capsys, monkeypatch
    ):
        """Even if active_profile is 'coder', setting JETTSTUI_HOME suppresses warning."""
        profile_dir = _default_home(tmp_path) / "profiles" / "coder"
        profile_dir.mkdir(parents=True)
        (_default_home(tmp_path) / "active_profile").write_text("coder\n")
        monkeypatch.setenv("JETTSTUI_HOME", str(profile_dir))

        result = fresh_constants.get_jettstui_home()

        assert result == profile_dir
        assert "JETTSTUI_HOME fallback" not in capsys.readouterr().err

    def test_unreadable_active_profile_no_crash(
        self, fresh_constants, tmp_path, capsys
    ):
        """active_profile that can't be decoded → fall through silently."""
        jettstui_dir = _default_home(tmp_path)
        jettstui_dir.mkdir()
        # Write bytes that aren't valid utf-8
        (jettstui_dir / "active_profile").write_bytes(b"\xff\xfe\x00\x00")

        result = fresh_constants.get_jettstui_home()

        assert result == _default_home(tmp_path)
        # Shouldn't crash; shouldn't warn either (can't tell what profile was intended)
        assert "JETTSTUI_HOME fallback" not in capsys.readouterr().err

    def test_empty_active_profile_no_warning(
        self, fresh_constants, tmp_path, capsys
    ):
        """Empty active_profile file → treated as default, no warning."""
        jettstui_dir = _default_home(tmp_path)
        jettstui_dir.mkdir()
        (jettstui_dir / "active_profile").write_text("")

        result = fresh_constants.get_jettstui_home()

        assert result == _default_home(tmp_path)
        assert "JETTSTUI_HOME fallback" not in capsys.readouterr().err
