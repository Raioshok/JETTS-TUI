"""Regression tests for _apply_profile_override JETTSTUI_HOME guard (issue #22502).

When JETTSTUI_HOME is set to the jettstui root (e.g. systemd hardcodes
JETTSTUI_HOME=/root/.jettstui), _apply_profile_override must still read
active_profile and update JETTSTUI_HOME to the profile directory.

When JETTSTUI_HOME is already a profile directory (.../profiles/<name>),
_apply_profile_override must trust it and return without re-reading
active_profile (child-process inheritance contract).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def _default_root(tmp_path: Path) -> Path:
    return tmp_path / ("jettstui" if sys.platform == "win32" else ".jettstui")


@pytest.fixture(autouse=True)
def _isolate_windows_default_root(tmp_path, monkeypatch):
    if sys.platform == "win32":
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))


def _run_apply_profile_override(
    tmp_path, monkeypatch, *, jettstui_home: str | None, active_profile: str | None,
    argv: list[str] | None = None,
):
    """Run _apply_profile_override in isolation.

    Returns the value of os.environ["JETTSTUI_HOME"] after the call,
    or None if unset.
    """
    jettstui_root = _default_root(tmp_path)
    jettstui_root.mkdir(parents=True, exist_ok=True)

    if active_profile is not None:
        (jettstui_root / "active_profile").write_text(active_profile)

    if active_profile and active_profile != "default":
        (jettstui_root / "profiles" / active_profile).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    if jettstui_home is not None:
        monkeypatch.setenv("JETTSTUI_HOME", jettstui_home)
    else:
        monkeypatch.delenv("JETTSTUI_HOME", raising=False)

    monkeypatch.setattr(sys, "argv", argv or ["jettstui", "gateway", "start"])

    from jettstui.main import _apply_profile_override
    _apply_profile_override()

    return os.environ.get("JETTSTUI_HOME")


class TestApplyProfileOverrideJettsTUIHomeGuard:
    """Regression guard for issue #22502.

    Verifies that JETTSTUI_HOME pointing to the jettstui root does NOT suppress
    the active_profile check, while JETTSTUI_HOME already pointing to a
    profile directory IS trusted as-is.
    """

    def test_jettstui_home_at_root_with_active_profile_is_redirected(
        self, tmp_path, monkeypatch
    ):
        """JETTSTUI_HOME=/root/.jettstui + active_profile=coder must redirect
        JETTSTUI_HOME to .../profiles/coder.

        Bug scenario from #22502: systemd sets JETTSTUI_HOME to the jettstui root
        and the user switches to a profile via `jettstui profile use`.
        Before the fix, the guard returned early and active_profile was ignored.
        """
        jettstui_root = _default_root(tmp_path)
        jettstui_root.mkdir(parents=True, exist_ok=True)

        result = _run_apply_profile_override(
            tmp_path,
            monkeypatch,
            jettstui_home=str(jettstui_root),
            active_profile="coder",
        )

        assert result is not None, "JETTSTUI_HOME must be set after profile redirect"
        assert "profiles" in result, (
            f"Expected JETTSTUI_HOME to point into profiles/ dir, got: {result!r}"
        )
        assert result.endswith("coder"), (
            f"Expected JETTSTUI_HOME to end with 'coder', got: {result!r}"
        )

    def test_jettstui_home_already_profile_dir_is_trusted(self, tmp_path, monkeypatch):
        """JETTSTUI_HOME=.../profiles/coder must not be overridden even when
        active_profile says something different.

        Preserves the child-process inheritance contract: a subprocess spawned
        with JETTSTUI_HOME already set to a specific profile must stay in that
        profile.
        """
        jettstui_root = _default_root(tmp_path)
        profile_dir = jettstui_root / "profiles" / "coder"
        profile_dir.mkdir(parents=True, exist_ok=True)

        (jettstui_root / "active_profile").write_text("other")

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("JETTSTUI_HOME", str(profile_dir))
        monkeypatch.setattr(sys, "argv", ["jettstui", "gateway", "start"])

        from jettstui.main import _apply_profile_override
        _apply_profile_override()

        assert os.environ.get("JETTSTUI_HOME") == str(profile_dir), (
            "JETTSTUI_HOME must remain unchanged when already pointing to a profile dir"
        )

    def test_jettstui_home_unset_reads_active_profile(self, tmp_path, monkeypatch):
        """Classic case: JETTSTUI_HOME unset + active_profile=coder must set
        JETTSTUI_HOME to the profile directory (existing behaviour must not regress).
        """
        result = _run_apply_profile_override(
            tmp_path,
            monkeypatch,
            jettstui_home=None,
            active_profile="coder",
        )

        assert result is not None
        assert "coder" in result

    @pytest.mark.skipif(sys.platform == "win32", reason="sudo and pwd are POSIX-only")
    def test_sudo_explicit_profile_resolves_invoking_users_profile(self, tmp_path, monkeypatch):
        """sudo elias ... should resolve `-p elias` under SUDO_USER, not root."""
        root_home = tmp_path / "root"
        user_home = tmp_path / "home" / "jettstui"
        profile_dir = user_home / ".jettstui" / "profiles" / "elias"
        profile_dir.mkdir(parents=True, exist_ok=True)
        (root_home / ".jettstui").mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(Path, "home", lambda: root_home)
        monkeypatch.setenv("SUDO_USER", "jettstui")
        monkeypatch.delenv("JETTSTUI_HOME", raising=False)
        monkeypatch.setattr(os, "geteuid", lambda: 0, raising=False)
        monkeypatch.setattr(sys, "argv", ["jettstui", "-p", "elias", "gateway", "install", "--system"])

        import pwd

        monkeypatch.setattr(pwd, "getpwnam", lambda name: SimpleNamespace(pw_dir=str(user_home)))

        from jettstui.main import _apply_profile_override
        _apply_profile_override()

        assert os.environ.get("JETTSTUI_HOME") == str(profile_dir)
        assert sys.argv == ["jettstui", "gateway", "install", "--system"]

    def test_jettstui_home_unset_default_profile_no_redirect(self, tmp_path, monkeypatch):
        """active_profile=default must not redirect JETTSTUI_HOME."""
        jettstui_root = _default_root(tmp_path)
        jettstui_root.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.delenv("JETTSTUI_HOME", raising=False)
        monkeypatch.setattr(sys, "argv", ["jettstui", "gateway", "start"])
        (jettstui_root / "active_profile").write_text("default")

        from jettstui.main import _apply_profile_override
        _apply_profile_override()

        assert os.environ.get("JETTSTUI_HOME") is None

    def test_subcommand_profile_flag_is_not_consumed(self, tmp_path, monkeypatch):
        """Command argv flags named --profile must stay with that command.

        Docker Desktop's MCP Toolkit uses `docker mcp gateway run --profile ...`.
        When that argv is passed through `jettstui mcp add --args`, the early
        profile pre-parser must not interpret the Docker profile as a JettsTUI
        profile.
        """
        jettstui_root = _default_root(tmp_path)
        jettstui_root.mkdir(parents=True, exist_ok=True)
        argv = [
            "jettstui",
            "mcp",
            "add",
            "docker-research",
            "--command",
            "docker",
            "--args",
            "mcp",
            "gateway",
            "run",
            "--profile",
            "research",
        ]

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.delenv("JETTSTUI_HOME", raising=False)
        monkeypatch.setattr(sys, "argv", list(argv))

        from jettstui.main import _apply_profile_override
        _apply_profile_override()

        assert os.environ.get("JETTSTUI_HOME") is None
        assert sys.argv == argv

    def test_profile_after_chat_subcommand_is_still_consumed(self, tmp_path, monkeypatch):
        """Profile flags historically work after normal JettsTUI subcommands."""
        result = _run_apply_profile_override(
            tmp_path,
            monkeypatch,
            jettstui_home=None,
            active_profile="coder",
            argv=["jettstui", "chat", "-p", "coder", "-q", "hello"],
        )

        assert result is not None
        assert result.endswith("coder")
        assert sys.argv == ["jettstui", "chat", "-q", "hello"]

    def test_top_level_profile_after_value_flag_is_consumed(self, tmp_path, monkeypatch):
        """Top-level --profile still works after other top-level value flags."""
        result = _run_apply_profile_override(
            tmp_path,
            monkeypatch,
            jettstui_home=None,
            active_profile="coder",
            argv=["jettstui", "-m", "gpt-5", "--profile", "coder", "chat"],
        )

        assert result is not None
        assert result.endswith("coder")
        assert sys.argv == ["jettstui", "-m", "gpt-5", "chat"]

    def test_top_level_profile_after_continue_flag_is_consumed(self, tmp_path, monkeypatch):
        """--continue has an optional value, so a following --profile is a flag."""
        result = _run_apply_profile_override(
            tmp_path,
            monkeypatch,
            jettstui_home=None,
            active_profile="coder",
            argv=["jettstui", "--continue", "--profile", "coder"],
        )

        assert result is not None
        assert result.endswith("coder")
        assert sys.argv == ["jettstui", "--continue"]


class TestSupervisedChildIgnoresStickyProfile:
    """The reserved default gateway s6 slot must not follow active_profile.

    Inside the Docker s6 image the ``gateway-default`` service slot runs a
    bare ``jettstui gateway run`` (no ``-p``) to mean "the root JETTSTUI_HOME
    profile". The run-script exports ``JETTSTUI_S6_SUPERVISED_CHILD=1``.
    Without a guard, ``_apply_profile_override`` would read the sticky
    ``active_profile`` file (set by e.g. the dashboard profile switcher) and
    redirect the reserved default gateway into that profile — producing a
    duplicate gateway for the active profile and no real default gateway.
    """

    def test_supervised_child_does_not_follow_active_profile(
        self, tmp_path, monkeypatch
    ):
        """JETTSTUI_S6_SUPERVISED_CHILD + active_profile=briefer must NOT redirect.

        Reproduces the Docker/profile scoping bug: the supervised default
        gateway is launched as bare ``jettstui gateway run`` with
        JETTSTUI_HOME=/opt/data (the container root, whose parent is NOT
        ``profiles``), and a sticky ``active_profile`` of another profile.
        The reserved default slot must stay on the root profile.
        """
        jettstui_root = _default_root(tmp_path)
        jettstui_root.mkdir(parents=True, exist_ok=True)
        (jettstui_root / "active_profile").write_text("briefer")
        (jettstui_root / "profiles" / "briefer").mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        # Container root JETTSTUI_HOME: parent dir is NOT "profiles", so the
        # #22502 guard does not short-circuit — step 2 (active_profile) runs.
        monkeypatch.setenv("JETTSTUI_HOME", str(jettstui_root))
        monkeypatch.setenv("JETTSTUI_S6_SUPERVISED_CHILD", "1")
        monkeypatch.setattr(sys, "argv", ["jettstui", "gateway", "run"])

        from jettstui.main import _apply_profile_override
        _apply_profile_override()

        assert os.environ.get("JETTSTUI_HOME") == str(jettstui_root), (
            "Supervised default gateway must stay on the root profile, not be "
            f"hijacked by active_profile; got {os.environ.get('JETTSTUI_HOME')!r}"
        )

    def test_non_supervised_run_still_follows_active_profile(
        self, tmp_path, monkeypatch
    ):
        """Without the sentinel, a normal `jettstui gateway run` still honors
        active_profile — the guard is scoped strictly to supervised children."""
        result = _run_apply_profile_override(
            tmp_path,
            monkeypatch,
            jettstui_home=None,
            active_profile="briefer",
            argv=["jettstui", "gateway", "run"],
        )

        assert result is not None
        assert result.endswith("briefer")

    def test_supervised_named_profile_flag_still_wins(self, tmp_path, monkeypatch):
        """A supervised named-profile slot passes ``-p <name>`` explicitly;
        that must still resolve (the sentinel guard only skips the sticky
        active_profile fallback, never an explicit flag)."""
        jettstui_root = _default_root(tmp_path)
        jettstui_root.mkdir(parents=True, exist_ok=True)
        (jettstui_root / "active_profile").write_text("briefer")
        (jettstui_root / "profiles" / "briefer").mkdir(parents=True, exist_ok=True)
        (jettstui_root / "profiles" / "coder").mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.delenv("JETTSTUI_HOME", raising=False)
        monkeypatch.setenv("JETTSTUI_S6_SUPERVISED_CHILD", "1")
        monkeypatch.setattr(sys, "argv", ["jettstui", "-p", "coder", "gateway", "run"])

        from jettstui.main import _apply_profile_override
        _apply_profile_override()

        result = os.environ.get("JETTSTUI_HOME")
        assert result is not None
        assert result.endswith("coder")

