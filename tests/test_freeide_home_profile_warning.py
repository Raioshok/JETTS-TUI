"""Tests for get_freeide_home() profile-mode fallback warning.

Regression test for https://github.com/freeide/freeide/issues/18594.

When FREEIDE_HOME is unset but an active_profile file indicates a non-default
profile is active, get_freeide_home() should:
  1. STILL return ~/.freeide (raising would brick 30+ module-level callers)
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
    """Import freeide_constants fresh and reset the one-shot warn flag."""
    import importlib
    import freeide_constants
    importlib.reload(freeide_constants)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("FREEIDE_HOME", raising=False)
    return freeide_constants


def _default_home(tmp_path: Path) -> Path:
    return tmp_path / ("jettstui" if sys.platform == "win32" else ".jettstui")


class TestGetFreeIDEHomeProfileWarning:
    def test_classic_mode_no_active_profile_no_warning(
        self, fresh_constants, tmp_path, capsys
    ):
        """Classic mode: no active_profile file → silent, returns ~/.freeide."""
        result = fresh_constants.get_freeide_home()
        assert result == _default_home(tmp_path)
        assert "FREEIDE_HOME fallback" not in capsys.readouterr().err

    def test_default_active_profile_no_warning(
        self, fresh_constants, tmp_path, capsys
    ):
        """active_profile=default → still no warning, returns ~/.freeide."""
        freeide_dir = _default_home(tmp_path)
        freeide_dir.mkdir()
        (freeide_dir / "active_profile").write_text("default\n")
        result = fresh_constants.get_freeide_home()
        assert result == _default_home(tmp_path)
        assert "FREEIDE_HOME fallback" not in capsys.readouterr().err

    def test_named_profile_unset_home_warns_once(
        self, fresh_constants, tmp_path, capsys
    ):
        """active_profile=coder + FREEIDE_HOME unset → warn loudly, still return fallback."""
        freeide_dir = _default_home(tmp_path)
        freeide_dir.mkdir()
        (freeide_dir / "active_profile").write_text("coder\n")

        result = fresh_constants.get_freeide_home()

        # 1. Still returns the fallback — no import-time crash
        assert result == _default_home(tmp_path)
        # 2. Stderr got the warning exactly once
        err = capsys.readouterr().err
        assert err.count("FREEIDE_HOME fallback") == 1
        assert "'coder'" in err
        assert "#18594" in err

        # 3. One-shot: second and third calls don't re-warn
        fresh_constants.get_freeide_home()
        fresh_constants.get_freeide_home()
        err2 = capsys.readouterr().err
        assert "FREEIDE_HOME fallback" not in err2

    def test_freeide_home_set_suppresses_warning(
        self, fresh_constants, tmp_path, capsys, monkeypatch
    ):
        """Even if active_profile is 'coder', setting FREEIDE_HOME suppresses warning."""
        profile_dir = _default_home(tmp_path) / "profiles" / "coder"
        profile_dir.mkdir(parents=True)
        (_default_home(tmp_path) / "active_profile").write_text("coder\n")
        monkeypatch.setenv("FREEIDE_HOME", str(profile_dir))

        result = fresh_constants.get_freeide_home()

        assert result == profile_dir
        assert "FREEIDE_HOME fallback" not in capsys.readouterr().err

    def test_unreadable_active_profile_no_crash(
        self, fresh_constants, tmp_path, capsys
    ):
        """active_profile that can't be decoded → fall through silently."""
        freeide_dir = _default_home(tmp_path)
        freeide_dir.mkdir()
        # Write bytes that aren't valid utf-8
        (freeide_dir / "active_profile").write_bytes(b"\xff\xfe\x00\x00")

        result = fresh_constants.get_freeide_home()

        assert result == _default_home(tmp_path)
        # Shouldn't crash; shouldn't warn either (can't tell what profile was intended)
        assert "FREEIDE_HOME fallback" not in capsys.readouterr().err

    def test_empty_active_profile_no_warning(
        self, fresh_constants, tmp_path, capsys
    ):
        """Empty active_profile file → treated as default, no warning."""
        freeide_dir = _default_home(tmp_path)
        freeide_dir.mkdir()
        (freeide_dir / "active_profile").write_text("")

        result = fresh_constants.get_freeide_home()

        assert result == _default_home(tmp_path)
        assert "FREEIDE_HOME fallback" not in capsys.readouterr().err
