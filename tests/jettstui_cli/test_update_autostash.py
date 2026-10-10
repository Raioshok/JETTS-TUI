from pathlib import Path
from subprocess import CalledProcessError
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from jettstui import config as jettstui_config
from jettstui import main as jettstui_main


# ---------------------------------------------------------------------------
# Managed-uv compatibility for tests that patch shutil.which
# ---------------------------------------------------------------------------
# The production code now uses ``ensure_uv()`` / ``update_managed_uv()``
# instead of ``shutil.which("uv")``.  Many tests in this file patch
# ``shutil.which`` to control whether uv is "available" — these autouse
# fixtures make the managed_uv functions delegate to the patched
# ``shutil.which`` so the existing test setup keeps working without
# per-test changes.
@pytest.fixture(autouse=True)
def _patch_managed_uv(request):
    """Make managed_uv helpers follow shutil.which mocking in tests."""
    import shutil

    # resolve_uv delegates to shutil.which("uv") so that test patches
    # on shutil.which flow through naturally.
    def _fake_resolve_uv(**kwargs):
        return shutil.which("uv")

    def _fake_ensure_uv(**kwargs):
        return shutil.which("uv")

    def _fake_update_managed_uv(**kwargs):
        return None  # never actually self-update in tests

    with patch("jettstui.managed_uv.resolve_uv", side_effect=_fake_resolve_uv), \
         patch("jettstui.managed_uv.ensure_uv", side_effect=_fake_ensure_uv), \
         patch("jettstui.managed_uv.update_managed_uv", side_effect=_fake_update_managed_uv):
        yield

def test_stash_local_changes_if_needed_returns_none_when_tree_clean(monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if cmd[-2:] == ["status", "--porcelain"]:
            return SimpleNamespace(stdout="", returncode=0)
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(jettstui_main.subprocess, "run", fake_run)

    stash_ref = jettstui_main._stash_local_changes_if_needed(["git"], tmp_path)

    assert stash_ref is None
    assert [cmd[-2:] for cmd, _ in calls] == [["status", "--porcelain"]]


def test_stash_local_changes_if_needed_returns_specific_stash_commit(monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if cmd[-2:] == ["status", "--porcelain"]:
            return SimpleNamespace(stdout=" M jettstui/main.py\n?? notes.txt\n", returncode=0)
        if cmd[-2:] == ["ls-files", "--unmerged"]:
            return SimpleNamespace(stdout="", returncode=0)
        if cmd[1:4] == ["stash", "push", "--include-untracked"]:
            return SimpleNamespace(stdout="Saved working directory\n", returncode=0)
        if cmd[-3:] == ["rev-parse", "--verify", "refs/stash"]:
            return SimpleNamespace(stdout="abc123\n", returncode=0)
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(jettstui_main.subprocess, "run", fake_run)

    stash_ref = jettstui_main._stash_local_changes_if_needed(["git"], tmp_path)

    assert stash_ref == "abc123"
    assert calls[1][0][-2:] == ["ls-files", "--unmerged"]
    # Pre-push probe of refs/stash (baseline for detecting a fresh entry),
    # then the push, then the post-push probe.
    assert calls[2][0][-3:] == ["rev-parse", "--verify", "refs/stash"]
    assert calls[3][0][1:4] == ["stash", "push", "--include-untracked"]
    assert calls[4][0][-3:] == ["rev-parse", "--verify", "refs/stash"]


def test_resolve_stash_selector_returns_matching_entry(monkeypatch, tmp_path):
    def fake_run(cmd, **kwargs):
        assert cmd == ["git", "stash", "list", "--format=%gd %H"]
        return SimpleNamespace(
            stdout="stash@{0} def456\nstash@{1} abc123\n",
            returncode=0,
        )

    monkeypatch.setattr(jettstui_main.subprocess, "run", fake_run)

    assert jettstui_main._resolve_stash_selector(["git"], tmp_path, "abc123") == "stash@{1}"



def test_restore_stashed_changes_prompts_before_applying(monkeypatch, tmp_path, capsys):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if cmd[1:3] == ["status", "--porcelain"]:
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        if cmd[1:3] == ["stash", "apply"]:
            return SimpleNamespace(stdout="applied\n", stderr="", returncode=0)
        if cmd[1:3] == ["diff", "--name-only"]:
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        if cmd[1:3] == ["stash", "list"]:
            return SimpleNamespace(stdout="stash@{1} abc123\n", stderr="", returncode=0)
        if cmd[1:3] == ["stash", "drop"]:
            return SimpleNamespace(stdout="dropped\n", stderr="", returncode=0)
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(jettstui_main.subprocess, "run", fake_run)
    monkeypatch.setattr("builtins.input", lambda: "")

    restored = jettstui_main._restore_stashed_changes(["git"], tmp_path, "abc123", prompt_user=True)

    assert restored is True
    assert [c for c, _ in calls] == [
        ["git", "status", "--porcelain"],
        ["git", "stash", "apply", "abc123"],
        ["git", "diff", "--name-only", "--diff-filter=U"],
        ["git", "stash", "list", "--format=%gd %H"],
        ["git", "stash", "drop", "stash@{1}"],
    ]
    out = capsys.readouterr().out
    assert "Restore local changes now? [Y/n]" in out
    assert "restored on top of the updated codebase" in out
    assert "git diff" in out
    assert "git status" in out


def test_restore_stashed_changes_can_skip_restore_and_keep_stash(monkeypatch, tmp_path, capsys):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(jettstui_main.subprocess, "run", fake_run)
    monkeypatch.setattr("builtins.input", lambda: "n")

    restored = jettstui_main._restore_stashed_changes(["git"], tmp_path, "abc123", prompt_user=True)

    assert restored is False
    assert calls == []
    out = capsys.readouterr().out
    assert "Restore local changes now? [Y/n]" in out
    assert "Your changes are still preserved in git stash." in out
    assert "git stash apply abc123" in out


def test_restore_stashed_changes_applies_without_prompt_when_disabled(monkeypatch, tmp_path, capsys):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if cmd[1:3] == ["status", "--porcelain"]:
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        if cmd[1:3] == ["stash", "apply"]:
            return SimpleNamespace(stdout="applied\n", stderr="", returncode=0)
        if cmd[1:3] == ["diff", "--name-only"]:
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        if cmd[1:3] == ["stash", "list"]:
            return SimpleNamespace(stdout="stash@{0} abc123\n", stderr="", returncode=0)
        if cmd[1:3] == ["stash", "drop"]:
            return SimpleNamespace(stdout="dropped\n", stderr="", returncode=0)
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(jettstui_main.subprocess, "run", fake_run)

    restored = jettstui_main._restore_stashed_changes(["git"], tmp_path, "abc123", prompt_user=False)

    assert restored is True
    assert [c for c, _ in calls] == [
        ["git", "status", "--porcelain"],
        ["git", "stash", "apply", "abc123"],
        ["git", "diff", "--name-only", "--diff-filter=U"],
        ["git", "stash", "list", "--format=%gd %H"],
        ["git", "stash", "drop", "stash@{0}"],
    ]
    assert "Restore local changes now?" not in capsys.readouterr().out



def test_print_stash_cleanup_guidance_with_selector(capsys):
    jettstui_main._print_stash_cleanup_guidance("abc123", "stash@{2}")

    out = capsys.readouterr().out
    assert "Check `git status` first" in out
    assert "git stash list --format='%gd %H %s'" in out
    assert "git stash drop stash@{2}" in out



def test_restore_stashed_changes_keeps_going_when_stash_entry_cannot_be_resolved(monkeypatch, tmp_path, capsys):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if cmd[1:3] == ["status", "--porcelain"]:
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        if cmd[1:3] == ["stash", "apply"]:
            return SimpleNamespace(stdout="applied\n", stderr="", returncode=0)
        if cmd[1:3] == ["diff", "--name-only"]:
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        if cmd[1:3] == ["stash", "list"]:
            return SimpleNamespace(stdout="stash@{0} def456\n", stderr="", returncode=0)
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(jettstui_main.subprocess, "run", fake_run)

    restored = jettstui_main._restore_stashed_changes(["git"], tmp_path, "abc123", prompt_user=False)

    assert restored is True
    _utf8 = {"encoding": "utf-8", "errors": "replace"}
    assert calls[0] == (["git", "status", "--porcelain"], {"cwd": tmp_path, "capture_output": True, "text": True, **_utf8})
    assert calls[1] == (["git", "stash", "apply", "abc123"], {"cwd": tmp_path, "capture_output": True, "text": True, **_utf8})
    assert calls[2] == (["git", "diff", "--name-only", "--diff-filter=U"], {"cwd": tmp_path, "capture_output": True, "text": True, **_utf8})
    assert calls[3] == (["git", "stash", "list", "--format=%gd %H"], {"cwd": tmp_path, "capture_output": True, "text": True, **_utf8, "check": True})
    out = capsys.readouterr().out
    assert "couldn't find the stash entry to drop" in out
    assert "stash was left in place" in out
    assert "Check `git status` first" in out
    assert "git stash list --format='%gd %H %s'" in out
    assert "Look for commit abc123" in out



def test_restore_stashed_changes_keeps_going_when_drop_fails(monkeypatch, tmp_path, capsys):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if cmd[1:3] == ["status", "--porcelain"]:
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        if cmd[1:3] == ["stash", "apply"]:
            return SimpleNamespace(stdout="applied\n", stderr="", returncode=0)
        if cmd[1:3] == ["diff", "--name-only"]:
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        if cmd[1:3] == ["stash", "list"]:
            return SimpleNamespace(stdout="stash@{0} abc123\n", stderr="", returncode=0)
        if cmd[1:3] == ["stash", "drop"]:
            return SimpleNamespace(stdout="", stderr="drop failed\n", returncode=1)
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(jettstui_main.subprocess, "run", fake_run)

    restored = jettstui_main._restore_stashed_changes(["git"], tmp_path, "abc123", prompt_user=False)

    assert restored is True
    assert calls[4][0] == ["git", "stash", "drop", "stash@{0}"]
    out = capsys.readouterr().out
    assert "couldn't drop the saved stash entry" in out
    assert "drop failed" in out
    assert "Check `git status` first" in out
    assert "git stash list --format='%gd %H %s'" in out
    assert "git stash drop stash@{0}" in out


def test_restore_stashed_changes_always_resets_on_conflict(monkeypatch, tmp_path, capsys):
    """Conflicts always auto-reset (no prompt) and return False, even interactively.

    Leaving conflict markers in source files makes jettstui unrunnable (SyntaxError).
    The stash is preserved for manual recovery; cmd_update continues normally.
    """
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if cmd[1:3] == ["status", "--porcelain"]:
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        if cmd[1:3] == ["stash", "apply"]:
            return SimpleNamespace(stdout="conflict output\n", stderr="conflict stderr\n", returncode=1)
        if cmd[1:3] == ["diff", "--name-only"]:
            return SimpleNamespace(stdout="jettstui/main.py\n", stderr="", returncode=0)
        if cmd[1:3] == ["reset", "--hard"]:
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(jettstui_main.subprocess, "run", fake_run)
    monkeypatch.setattr("builtins.input", lambda: "y")

    result = jettstui_main._restore_stashed_changes(["git"], tmp_path, "abc123", prompt_user=True)

    assert result is False
    out = capsys.readouterr().out
    assert "Conflicted files:" in out
    assert "jettstui/main.py" in out
    assert "stashed changes are preserved" in out
    assert "Working tree reset to clean state" in out
    assert "git stash apply abc123" in out
    reset_calls = [c for c, _ in calls if c[1:3] == ["reset", "--hard"]]
    assert len(reset_calls) == 1


def test_restore_stashed_changes_auto_resets_non_interactive(monkeypatch, tmp_path, capsys):
    """Non-interactive mode auto-resets without prompting and returns False
    instead of sys.exit(1) so the update can continue (gateway /update path)."""
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if cmd[1:3] == ["status", "--porcelain"]:
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        if cmd[1:3] == ["stash", "apply"]:
            return SimpleNamespace(stdout="applied\n", stderr="", returncode=0)
        if cmd[1:3] == ["diff", "--name-only"]:
            return SimpleNamespace(stdout="cli.py\n", stderr="", returncode=0)
        if cmd[1:3] == ["reset", "--hard"]:
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(jettstui_main.subprocess, "run", fake_run)

    result = jettstui_main._restore_stashed_changes(["git"], tmp_path, "abc123", prompt_user=False)

    assert result is False
    out = capsys.readouterr().out
    assert "Working tree reset to clean state" in out
    reset_calls = [c for c, _ in calls if c[1:3] == ["reset", "--hard"]]
    assert len(reset_calls) == 1


@pytest.mark.parametrize("status, returncode", [(" M changed.py\n", 0), ("", 128)])
def test_restore_stashed_changes_preserves_new_work_before_apply(
    monkeypatch, tmp_path, capsys, status, returncode
):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        assert cmd == ["git", "status", "--porcelain"]
        return SimpleNamespace(stdout=status, stderr="status failed", returncode=returncode)

    monkeypatch.setattr(jettstui_main.subprocess, "run", fake_run)

    assert jettstui_main._restore_stashed_changes(
        ["git"], tmp_path, "abc123", prompt_user=False
    ) is False
    assert calls == [["git", "status", "--porcelain"]]
    output = capsys.readouterr().out
    assert "stash restore skipped for safety" in output
    assert "abc123" in output


def test_restore_stashed_changes_does_not_touch_post_stash_edit_real_git(tmp_path):
    """An actual Git checkout must retain edits made while an update runs."""
    import shutil
    import subprocess

    if shutil.which("git") is None:
        pytest.skip("git not available")

    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=tmp_path, capture_output=True, text=True, check=True
        ).stdout.strip()

    git("init", "-q")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test")
    target = tmp_path / "code.py"
    target.write_text("base\n", encoding="utf-8")
    git("add", "code.py")
    git("commit", "-qm", "base")
    target.write_text("stashed\n", encoding="utf-8")
    git("stash", "push", "-m", "update backup")
    stash_ref = git("rev-parse", "refs/stash")
    target.write_text("new work\n", encoding="utf-8")

    assert jettstui_main._restore_stashed_changes(
        ["git"], tmp_path, stash_ref, prompt_user=False
    ) is False
    assert target.read_text(encoding="utf-8") == "new work\n"
    assert git("rev-parse", "refs/stash") == stash_ref


def test_stash_local_changes_if_needed_raises_when_stash_ref_missing(monkeypatch, tmp_path):
    def fake_run(cmd, **kwargs):
        if cmd[-2:] == ["status", "--porcelain"]:
            return SimpleNamespace(stdout=" M jettstui/main.py\n", returncode=0)
        if cmd[-2:] == ["ls-files", "--unmerged"]:
            return SimpleNamespace(stdout="", returncode=0)
        if cmd[1:4] == ["stash", "push", "--include-untracked"]:
            return SimpleNamespace(stdout="Saved working directory\n", returncode=0)
        if cmd[-3:] == ["rev-parse", "--verify", "refs/stash"]:
            raise CalledProcessError(returncode=128, cmd=cmd)
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(jettstui_main.subprocess, "run", fake_run)

    with pytest.raises(CalledProcessError):
        jettstui_main._stash_local_changes_if_needed(["git"], Path(tmp_path))


def test_discard_lockfile_churn_skips_lock_when_package_json_dirty(tmp_path):
    """Intentional dependency edits update package.json and lockfile together."""
    import shutil
    import subprocess

    if shutil.which("git") is None:
        pytest.skip("git not available")

    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=tmp_path, capture_output=True, text=True, check=True
        )

    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (tmp_path / "package.json").write_text('{"dependencies":{"a":"1"}}\n')
    (tmp_path / "package-lock.json").write_text('{"lock":"old"}\n')
    git("add", "package.json", "package-lock.json")
    git("commit", "-qm", "init")

    (tmp_path / "package.json").write_text('{"dependencies":{"a":"2"}}\n')
    (tmp_path / "package-lock.json").write_text('{"lock":"new"}\n')

    jettstui_main._discard_lockfile_churn(["git"], tmp_path)

    assert (tmp_path / "package-lock.json").read_text() == '{"lock":"new"}\n'


def test_discard_lockfile_churn_restores_lock_when_package_json_clean(tmp_path):
    """Runtime npm lockfile rewrites are still discarded on managed updates."""
    import shutil
    import subprocess

    if shutil.which("git") is None:
        pytest.skip("git not available")

    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=tmp_path, capture_output=True, text=True, check=True
        )

    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (tmp_path / "package.json").write_text('{"dependencies":{"a":"1"}}\n')
    (tmp_path / "package-lock.json").write_text('{"lock":"old"}\n')
    git("add", "package.json", "package-lock.json")
    git("commit", "-qm", "init")

    (tmp_path / "package-lock.json").write_text('{"lock":"runtime-churn"}\n')

    jettstui_main._discard_lockfile_churn(["git"], tmp_path)

    assert (tmp_path / "package-lock.json").read_text() == '{"lock":"old"}\n'


# ---------------------------------------------------------------------------
# Update uses .[all] with fallback to .
# ---------------------------------------------------------------------------

def _setup_update_mocks(monkeypatch, tmp_path):
    """Common setup for cmd_update tests."""
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(jettstui_main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(jettstui_main, "_pause_windows_gateways_for_update", lambda: [])
    monkeypatch.setattr(jettstui_main, "_stash_local_changes_if_needed", lambda *a, **kw: None)
    monkeypatch.setattr(jettstui_main, "_restore_stashed_changes", lambda *a, **kw: True)
    monkeypatch.setattr(jettstui_config, "get_missing_env_vars", lambda required_only=True: [])
    monkeypatch.setattr(jettstui_config, "get_missing_config_fields", lambda: [])
    monkeypatch.setattr(jettstui_config, "check_config_version", lambda: (5, 5))
    monkeypatch.setattr(jettstui_config, "migrate_config", lambda **kw: {"env_added": [], "config_added": []})
    monkeypatch.setattr(jettstui_main, "_upgrade_pip_before_lazy_refresh", lambda *a, **kw: None)
    monkeypatch.setattr(jettstui_main, "_refresh_active_lazy_features", lambda *a, **kw: True)


def test_cmd_update_retries_optional_extras_individually_when_all_fails(monkeypatch, tmp_path, capsys):
    """When .[all] fails, update should keep base deps and retry extras individually."""
    _setup_update_mocks(monkeypatch, tmp_path)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/uv" if name == "uv" else None)
    monkeypatch.setattr(jettstui_main, "_is_termux_env", lambda env=None: False)
    monkeypatch.setattr(jettstui_main, "_load_installable_optional_extras", lambda group="all": ["matrix", "mcp"])

    recorded = []

    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["git", "-c", "windows.appendAtomically=false"]:
            cmd = ["git", *cmd[3:]]
        recorded.append(cmd)
        if cmd == ["git", "fetch", "--no-write-fetch-head", "origin", "+refs/heads/main:refs/remotes/origin/main"]:
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        if cmd == ["git", "rev-parse", "--abbrev-ref", "HEAD"]:
            return SimpleNamespace(stdout="main\n", stderr="", returncode=0)
        if cmd == ["git", "rev-list", "HEAD..origin/main", "--count"]:
            return SimpleNamespace(stdout="1\n", stderr="", returncode=0)
        if cmd == ["git", "pull", "--ff-only", "origin", "main"]:
            return SimpleNamespace(stdout="Updating\n", stderr="", returncode=0)
        if cmd == ["/usr/bin/uv", "pip", "install", "-e", ".[all]"]:
            raise CalledProcessError(returncode=1, cmd=cmd)
        if cmd == ["/usr/bin/uv", "pip", "install", "-e", "."]:
            return SimpleNamespace(returncode=0)
        if cmd == ["/usr/bin/uv", "pip", "install", "-e", ".[matrix]"]:
            raise CalledProcessError(returncode=1, cmd=cmd)
        if cmd == ["/usr/bin/uv", "pip", "install", "-e", ".[mcp]"]:
            return SimpleNamespace(returncode=0)
        # Catch-all must include stdout/stderr so consumers that parse
        # output (e.g. the dashboard-restart `ps -A` scan added in the
        # updater) don't crash on AttributeError.
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(jettstui_main.subprocess, "run", fake_run)

    jettstui_main.cmd_update(SimpleNamespace())

    install_cmds = [c for c in recorded if "pip" in c and "install" in c]
    assert install_cmds == [
        ["/usr/bin/uv", "pip", "install", "-e", ".[all]"],
        ["/usr/bin/uv", "pip", "install", "-e", "."],
        ["/usr/bin/uv", "pip", "install", "-e", ".[matrix]"],
        ["/usr/bin/uv", "pip", "install", "-e", ".[mcp]"],
    ]

    out = capsys.readouterr().out
    assert "retrying extras individually" in out
    assert "Reinstalled optional extras individually: mcp" in out
    assert "Skipped optional extras that still failed: matrix" in out


def test_cmd_update_succeeds_with_extras(monkeypatch, tmp_path):
    """When .[all] succeeds, no fallback should be attempted."""
    _setup_update_mocks(monkeypatch, tmp_path)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/uv" if name == "uv" else None)
    monkeypatch.setattr(jettstui_main, "_is_termux_env", lambda env=None: False)

    recorded = []

    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["git", "-c", "windows.appendAtomically=false"]:
            cmd = ["git", *cmd[3:]]
        recorded.append(cmd)
        if cmd == ["git", "fetch", "--no-write-fetch-head", "origin", "+refs/heads/main:refs/remotes/origin/main"]:
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        if cmd == ["git", "rev-parse", "--abbrev-ref", "HEAD"]:
            return SimpleNamespace(stdout="main\n", stderr="", returncode=0)
        if cmd == ["git", "rev-list", "HEAD..origin/main", "--count"]:
            return SimpleNamespace(stdout="1\n", stderr="", returncode=0)
        if cmd == ["git", "pull", "--ff-only", "origin", "main"]:
            return SimpleNamespace(stdout="Updating\n", stderr="", returncode=0)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(jettstui_main.subprocess, "run", fake_run)

    jettstui_main.cmd_update(SimpleNamespace())

    install_cmds = [c for c in recorded if "pip" in c and "install" in c]
    assert len(install_cmds) == 1
    assert ".[all]" in install_cmds[0]


def test_refresh_active_memory_provider_dependencies_reinstalls_active_provider(monkeypatch):
    """#53272/#70636: update must re-run the active provider's dep install."""
    recorded = []

    monkeypatch.setattr(
        "jettstui.config.load_config",
        lambda: {"memory": {"provider": "mem0"}},
    )
    monkeypatch.setattr(
        "jettstui.memory_setup._install_dependencies",
        lambda provider_name, force=False: recorded.append((provider_name, force)),
    )

    jettstui_main._refresh_active_memory_provider_dependencies()

    assert recorded == [("mem0", True)]


@pytest.mark.parametrize(
    "memory_cfg",
    [
        {},                                          # no provider configured
        {"provider": ""},                            # empty provider
        {"provider": "default"},                     # built-in store
        {"provider": "mem0", "enabled": False},      # memory disabled
    ],
)
def test_refresh_active_memory_provider_dependencies_skips_inactive(monkeypatch, memory_cfg):
    recorded = []

    monkeypatch.setattr(
        "jettstui.config.load_config",
        lambda: {"memory": memory_cfg},
    )
    monkeypatch.setattr(
        "jettstui.memory_setup._install_dependencies",
        lambda provider_name, force=False: recorded.append((provider_name, force)),
    )

    jettstui_main._refresh_active_memory_provider_dependencies()

    assert recorded == []


def test_refresh_active_memory_provider_dependencies_never_raises(monkeypatch):
    """A provider install failure must not block the rest of the update."""
    monkeypatch.setattr(
        "jettstui.config.load_config",
        lambda: {"memory": {"provider": "hindsight"}},
    )

    def boom(provider_name, force=False):
        raise RuntimeError("pip exploded")

    monkeypatch.setattr("jettstui.memory_setup._install_dependencies", boom)

    jettstui_main._refresh_active_memory_provider_dependencies()  # must not raise


def test_cmd_update_refreshes_active_memory_provider_dependencies(monkeypatch, tmp_path):
    """The git-pull update path must invoke the memory-provider refresh."""
    _setup_update_mocks(monkeypatch, tmp_path)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/uv" if name == "uv" else None)
    monkeypatch.setattr(jettstui_main, "_is_termux_env", lambda env=None: False)

    refresh_calls = []
    monkeypatch.setattr(
        jettstui_main,
        "_refresh_active_memory_provider_dependencies",
        lambda: refresh_calls.append(True),
    )

    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["git", "-c", "windows.appendAtomically=false"]:
            cmd = ["git", *cmd[3:]]
        if cmd == ["git", "rev-parse", "--abbrev-ref", "HEAD"]:
            return SimpleNamespace(stdout="main\n", stderr="", returncode=0)
        if cmd == ["git", "rev-list", "HEAD..origin/main", "--count"]:
            return SimpleNamespace(stdout="1\n", stderr="", returncode=0)
        if cmd == ["git", "pull", "--ff-only", "origin", "main"]:
            return SimpleNamespace(stdout="Updating\n", stderr="", returncode=0)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(jettstui_main.subprocess, "run", fake_run)

    jettstui_main.cmd_update(SimpleNamespace())

    assert refresh_calls == [True]


def test_cmd_update_reloads_runtime_modules_before_lazy_refresh(monkeypatch, tmp_path):
    """Lazy refresh must not see pre-pull modules cached in this process."""
    _setup_update_mocks(monkeypatch, tmp_path)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/uv" if name == "uv" else None)
    monkeypatch.setattr(jettstui_main, "_is_termux_env", lambda env=None: False)

    events = []

    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["git", "-c", "windows.appendAtomically=false"]:
            cmd = ["git", *cmd[3:]]
        if cmd == ["git", "fetch", "--no-write-fetch-head", "origin", "+refs/heads/main:refs/remotes/origin/main"]:
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        if cmd == ["git", "rev-parse", "--abbrev-ref", "HEAD"]:
            return SimpleNamespace(stdout="main\n", stderr="", returncode=0)
        if cmd == ["git", "rev-list", "HEAD..origin/main", "--count"]:
            return SimpleNamespace(stdout="1\n", stderr="", returncode=0)
        if cmd == ["git", "pull", "--ff-only", "origin", "main"]:
            events.append("pull")
            return SimpleNamespace(stdout="Updating\n", stderr="", returncode=0)
        if "pip" in cmd and "install" in cmd:
            events.append("install")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def fake_reload_runtime_modules():
        events.append("reload")

    def fake_refresh_lazy_features(install_prefix=None, env=None):
        events.append("lazy-refresh")
        return True

    monkeypatch.setattr(jettstui_main.subprocess, "run", fake_run)
    monkeypatch.setattr(jettstui_main, "_reload_updated_runtime_modules", fake_reload_runtime_modules)
    monkeypatch.setattr(jettstui_main, "_refresh_active_lazy_features", fake_refresh_lazy_features)

    jettstui_main.cmd_update(SimpleNamespace())

    assert (
        events.index("pull")
        < events.index("install")
        < events.index("reload")
        < events.index("lazy-refresh")
    )


def test_reload_updated_runtime_modules_restores_new_jettstui_constants_symbol(monkeypatch):
    """A pre-pull module object missing a new helper is repaired by reload."""
    import jettstui_constants

    monkeypatch.delattr(jettstui_constants, "apply_subprocess_home_env", raising=False)
    assert not hasattr(jettstui_constants, "apply_subprocess_home_env")

    jettstui_main._reload_updated_runtime_modules()

    assert callable(jettstui_constants.apply_subprocess_home_env)


def test_install_with_optional_fallback_honors_custom_group(monkeypatch):
    """Termux update path should target .[termux-all] when requested."""
    calls = []
    monkeypatch.setattr(
        jettstui_main,
        "_load_installable_optional_extras",
        lambda group="all": ["termux", "mcp"] if group == "termux-all" else [],
    )

    def fake_run_with_heartbeat(cmd, **kwargs):
        calls.append(cmd)
        if cmd[-1] == ".[termux-all]":
            raise CalledProcessError(returncode=1, cmd=cmd)
        return None

    monkeypatch.setattr(jettstui_main, "_run_install_with_heartbeat", fake_run_with_heartbeat)

    jettstui_main._install_python_dependencies_with_optional_fallback(
        ["/usr/bin/uv", "pip"],
        group="termux-all",
    )

    assert calls == [
        ["/usr/bin/uv", "pip", "install", "-e", ".[termux-all]"],
        ["/usr/bin/uv", "pip", "install", "-e", "."],
        ["/usr/bin/uv", "pip", "install", "-e", ".[termux]"],
        ["/usr/bin/uv", "pip", "install", "-e", ".[mcp]"],
    ]


def test_install_heartbeat_prints_when_dependency_install_is_silent(monkeypatch, capsys):
    """Long quiet installs should emit periodic heartbeat lines."""

    def fake_run(cmd, **kwargs):
        jettstui_main._time.sleep(1.2)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(jettstui_main.subprocess, "run", fake_run)

    jettstui_main._run_install_with_heartbeat(
        ["uv", "pip", "install", "-e", "."],
        heartbeat_interval_seconds=1,
    )

    out = capsys.readouterr().out
    assert "still installing dependencies" in out


# ---------------------------------------------------------------------------
# ff-only fallback to reset --hard on diverged history
# ---------------------------------------------------------------------------

def _make_update_side_effect(
    current_branch="main",
    commit_count="3",
    ff_only_fails=False,
    reset_fails=False,
    fetch_fails=False,
    fetch_stderr="",
):
    """Build a subprocess.run side_effect for cmd_update tests."""
    recorded = []

    def side_effect(cmd, **kwargs):
        if cmd[:3] == ["git", "-c", "windows.appendAtomically=false"]:
            cmd = ["git", *cmd[3:]]
        recorded.append(cmd)
        joined = " ".join(str(c) for c in cmd)
        if "fetch" in joined and "origin" in joined:
            if fetch_fails:
                return SimpleNamespace(stdout="", stderr=fetch_stderr, returncode=128)
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        if "rev-parse" in joined and "--abbrev-ref" in joined:
            return SimpleNamespace(stdout=f"{current_branch}\n", stderr="", returncode=0)
        if "checkout" in joined and "main" in joined:
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        if "rev-list" in joined:
            return SimpleNamespace(stdout=f"{commit_count}\n", stderr="", returncode=0)
        if "--ff-only" in joined:
            if ff_only_fails:
                return SimpleNamespace(
                    stdout="",
                    stderr="fatal: Not possible to fast-forward, aborting.\n",
                    returncode=128,
                )
            return SimpleNamespace(stdout="Updating abc..def\n", stderr="", returncode=0)
        if "reset" in joined and "--hard" in joined:
            if reset_fails:
                return SimpleNamespace(stdout="", stderr="error: unable to write\n", returncode=1)
            return SimpleNamespace(stdout="HEAD is now at abc123\n", stderr="", returncode=0)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    return side_effect, recorded


def test_cmd_update_falls_back_to_reset_when_ff_only_fails(monkeypatch, tmp_path, capsys):
    """When --ff-only fails (diverged history), update resets to origin/{branch}."""
    _setup_update_mocks(monkeypatch, tmp_path)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/uv" if name == "uv" else None)

    side_effect, recorded = _make_update_side_effect(ff_only_fails=True)
    monkeypatch.setattr(jettstui_main.subprocess, "run", side_effect)

    jettstui_main.cmd_update(SimpleNamespace())

    reset_calls = [c for c in recorded if "reset" in c and "--hard" in c]
    assert len(reset_calls) == 1
    assert reset_calls[0] == ["git", "reset", "--hard", "origin/main"]

    out = capsys.readouterr().out
    assert "Fast-forward not possible" in out


def test_cmd_update_no_reset_when_ff_only_succeeds(monkeypatch, tmp_path):
    """When --ff-only succeeds, no reset is attempted."""
    _setup_update_mocks(monkeypatch, tmp_path)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/uv" if name == "uv" else None)

    side_effect, recorded = _make_update_side_effect()
    monkeypatch.setattr(jettstui_main.subprocess, "run", side_effect)

    jettstui_main.cmd_update(SimpleNamespace())

    reset_calls = [c for c in recorded if "reset" in c and "--hard" in c]
    assert len(reset_calls) == 0


# ---------------------------------------------------------------------------
# Non-main branch → auto-checkout main
# ---------------------------------------------------------------------------

def test_cmd_update_switches_to_main_from_feature_branch(monkeypatch, tmp_path, capsys):
    """When on a feature branch, update checks out main before pulling."""
    _setup_update_mocks(monkeypatch, tmp_path)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/uv" if name == "uv" else None)

    side_effect, recorded = _make_update_side_effect(current_branch="fix/something")
    monkeypatch.setattr(jettstui_main.subprocess, "run", side_effect)

    jettstui_main.cmd_update(SimpleNamespace())

    checkout_calls = [c for c in recorded if "checkout" in c and "main" in c]
    assert len(checkout_calls) == 1

    out = capsys.readouterr().out
    assert "fix/something" in out
    assert "switching to main" in out


def test_cmd_update_switches_to_main_from_detached_head(monkeypatch, tmp_path, capsys):
    """When in detached HEAD state, update checks out main before pulling."""
    _setup_update_mocks(monkeypatch, tmp_path)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/uv" if name == "uv" else None)

    side_effect, recorded = _make_update_side_effect(current_branch="HEAD")
    monkeypatch.setattr(jettstui_main.subprocess, "run", side_effect)

    jettstui_main.cmd_update(SimpleNamespace())

    checkout_calls = [c for c in recorded if "checkout" in c and "main" in c]
    assert len(checkout_calls) == 1

    out = capsys.readouterr().out
    assert "detached HEAD" in out


def test_cmd_update_restores_stash_and_stays_on_main_when_already_up_to_date(monkeypatch, tmp_path, capsys):
    """On another branch with nothing new on main: stash restored, install stays on main.

    Switching back left installs stranded on a stale branch forever, because
    this path only runs when main has nothing new to pull.
    """
    _setup_update_mocks(monkeypatch, tmp_path)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/uv" if name == "uv" else None)

    # Enable stash so it returns a ref
    monkeypatch.setattr(
        jettstui_main, "_stash_local_changes_if_needed",
        lambda *a, **kw: "abc123deadbeef",
    )
    restore_calls = []
    monkeypatch.setattr(
        jettstui_main, "_restore_stashed_changes",
        lambda *a, **kw: restore_calls.append(1) or True,
    )

    side_effect, recorded = _make_update_side_effect(
        current_branch="fix/something", commit_count="0",
    )
    monkeypatch.setattr(jettstui_main.subprocess, "run", side_effect)

    jettstui_main.cmd_update(SimpleNamespace())

    # Stash should have been restored
    assert len(restore_calls) == 1

    checkout_back = [c for c in recorded if "checkout" in c and "fix/something" in c]
    assert checkout_back == []

    out = capsys.readouterr().out
    assert "Already up to date" in out


def test_cmd_update_switching_branch_runs_full_update_without_new_commits(monkeypatch, tmp_path, capsys):
    """Moving onto main changes the code on disk, so it is an update even when
    main has nothing new to pull (the stale ``codex/...`` install case)."""
    _setup_update_mocks(monkeypatch, tmp_path)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/uv" if name == "uv" else None)

    base_side_effect, recorded = _make_update_side_effect(
        current_branch="codex/release-hardening", commit_count="0",
    )
    head = {"sha": "old-branch-sha"}

    def side_effect(cmd, **kwargs):
        joined = " ".join(str(c) for c in cmd)
        if "checkout" in joined and "main" in joined:
            head["sha"] = "main-sha"
        if joined.endswith("rev-parse HEAD"):
            recorded.append(cmd)
            return SimpleNamespace(stdout=f"{head['sha']}\n", stderr="", returncode=0)
        return base_side_effect(cmd, **kwargs)

    monkeypatch.setattr(jettstui_main.subprocess, "run", side_effect)

    jettstui_main.cmd_update(SimpleNamespace())

    out = capsys.readouterr().out
    assert "Already up to date" not in out
    assert "Switched to main" in out
    assert not [c for c in recorded if "checkout" in c and "codex/release-hardening" in c]


def test_cmd_update_no_checkout_when_already_on_main(monkeypatch, tmp_path):
    """When already on main, no checkout is needed."""
    _setup_update_mocks(monkeypatch, tmp_path)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/uv" if name == "uv" else None)

    side_effect, recorded = _make_update_side_effect()
    monkeypatch.setattr(jettstui_main.subprocess, "run", side_effect)

    jettstui_main.cmd_update(SimpleNamespace())

    checkout_calls = [c for c in recorded if "checkout" in c]
    assert len(checkout_calls) == 0


def test_cmd_update_fetch_is_scoped_to_target_branch(monkeypatch, tmp_path):
    """The update fetch must name the target branch. A bare `git fetch origin`
    pulls every ref, and this repo has thousands of auto-generated branches, so
    an unscoped fetch can stall for minutes on a non-single-branch checkout."""
    _setup_update_mocks(monkeypatch, tmp_path)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/uv" if name == "uv" else None)

    side_effect, recorded = _make_update_side_effect()
    monkeypatch.setattr(jettstui_main.subprocess, "run", side_effect)

    jettstui_main.cmd_update(SimpleNamespace())

    fetch_calls = [c for c in recorded if "fetch" in c]
    assert fetch_calls == [["git", "fetch", "--no-write-fetch-head", "origin", "+refs/heads/main:refs/remotes/origin/main"]]
    assert ["git", "fetch", "origin"] not in recorded


# ---------------------------------------------------------------------------
# Fetch failure — friendly error messages
# ---------------------------------------------------------------------------

def test_cmd_update_network_error_shows_friendly_message(monkeypatch, tmp_path, capsys):
    """Network failures during fetch show a user-friendly message."""
    _setup_update_mocks(monkeypatch, tmp_path)

    side_effect, _ = _make_update_side_effect(
        fetch_fails=True,
        fetch_stderr="fatal: unable to access 'https://...': Could not resolve host: github.com",
    )
    monkeypatch.setattr(jettstui_main.subprocess, "run", side_effect)

    with pytest.raises(SystemExit, match="1"):
        jettstui_main.cmd_update(SimpleNamespace())

    out = capsys.readouterr().out
    assert "Network error" in out


def test_cmd_update_auth_error_shows_friendly_message(monkeypatch, tmp_path, capsys):
    """Auth failures during fetch show a user-friendly message."""
    _setup_update_mocks(monkeypatch, tmp_path)

    side_effect, _ = _make_update_side_effect(
        fetch_fails=True,
        fetch_stderr="fatal: Authentication failed for 'https://...'",
    )
    monkeypatch.setattr(jettstui_main.subprocess, "run", side_effect)

    with pytest.raises(SystemExit, match="1"):
        jettstui_main.cmd_update(SimpleNamespace())

    out = capsys.readouterr().out
    assert "Authentication failed" in out


# ---------------------------------------------------------------------------
# reset --hard failure — don't attempt stash restore
# ---------------------------------------------------------------------------

def test_cmd_update_skips_stash_restore_when_reset_fails(monkeypatch, tmp_path, capsys):
    """When reset --hard fails, stash restore is skipped with a helpful message."""
    _setup_update_mocks(monkeypatch, tmp_path)
    # Re-enable stash so it actually returns a ref
    monkeypatch.setattr(
        jettstui_main, "_stash_local_changes_if_needed",
        lambda *a, **kw: "abc123deadbeef",
    )
    restore_calls = []
    monkeypatch.setattr(
        jettstui_main, "_restore_stashed_changes",
        lambda *a, **kw: restore_calls.append(1) or True,
    )

    side_effect, _ = _make_update_side_effect(ff_only_fails=True, reset_fails=True)
    monkeypatch.setattr(jettstui_main.subprocess, "run", side_effect)

    with pytest.raises(SystemExit, match="1"):
        jettstui_main.cmd_update(SimpleNamespace())

    # Stash restore should NOT have been called
    assert len(restore_calls) == 0

    out = capsys.readouterr().out
    assert "preserved in stash" in out


# ---------------------------------------------------------------------------
# Non-interactive update.non_interactive_local_changes setting
# (chat app / gateway): "discard" throws stashed changes away, "stash"
# (default) restores them. Interactive terminal updates ignore the setting
# and always go through the restore path.
# ---------------------------------------------------------------------------

def _setup_setting_test(monkeypatch, tmp_path, mode):
    """Common wiring: real stash returns a ref, restore + discard are
    recorded, and load_config reports the given non_interactive_local_changes
    mode."""
    _setup_update_mocks(monkeypatch, tmp_path)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/uv" if name == "uv" else None)
    monkeypatch.setattr(
        jettstui_main, "_stash_local_changes_if_needed",
        lambda *a, **kw: "abc123deadbeef",
    )
    restore_calls = []
    discard_calls = []
    monkeypatch.setattr(
        jettstui_main, "_restore_stashed_changes",
        lambda *a, **kw: restore_calls.append(1) or True,
    )
    monkeypatch.setattr(
        jettstui_main, "_discard_stashed_changes",
        lambda *a, **kw: discard_calls.append(1) or True,
    )
    monkeypatch.setattr(
        jettstui_config, "load_config",
        lambda *a, **kw: {"updates": {"non_interactive_local_changes": mode}},
    )
    side_effect, recorded = _make_update_side_effect()
    monkeypatch.setattr(jettstui_main.subprocess, "run", side_effect)
    return restore_calls, discard_calls, recorded


def test_non_interactive_discard_throws_changes_away(monkeypatch, tmp_path):
    """Gateway/chat-app update with discard mode drops the stash, never restores."""
    restore_calls, discard_calls, _ = _setup_setting_test(monkeypatch, tmp_path, "discard")

    jettstui_main.cmd_update(SimpleNamespace(gateway=True))

    assert len(discard_calls) == 1
    assert len(restore_calls) == 0


def test_non_interactive_stash_restores_changes(monkeypatch, tmp_path):
    """Gateway/chat-app update with the default stash mode restores, never discards."""
    restore_calls, discard_calls, _ = _setup_setting_test(monkeypatch, tmp_path, "stash")

    jettstui_main.cmd_update(SimpleNamespace(gateway=True))

    assert len(restore_calls) == 1
    assert len(discard_calls) == 0


def test_interactive_update_ignores_discard_setting(monkeypatch, tmp_path):
    """An interactive (TTY) terminal update always restores — the discard
    setting only governs non-interactive updates."""
    restore_calls, discard_calls, _ = _setup_setting_test(monkeypatch, tmp_path, "discard")
    # Force an interactive TTY so _non_interactive_update is False even though
    # the config says discard.
    monkeypatch.setattr(jettstui_main.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(jettstui_main.sys.stdout, "isatty", lambda: True)

    jettstui_main.cmd_update(SimpleNamespace())  # no gateway, no --yes

    assert len(restore_calls) == 1
    assert len(discard_calls) == 0


def test_non_interactive_defaults_to_stash_when_setting_absent(monkeypatch, tmp_path):
    """A config with no update section falls back to stash (safe default)."""
    restore_calls, discard_calls, _ = _setup_setting_test(monkeypatch, tmp_path, "stash")
    # Override load_config to return a config with NO update section at all.
    monkeypatch.setattr(jettstui_config, "load_config", lambda *a, **kw: {"model": {}})

    jettstui_main.cmd_update(SimpleNamespace(gateway=True))

    assert len(restore_calls) == 1
    assert len(discard_calls) == 0


def test_bootstrap_marker_not_autostashed_by_update(tmp_path):
    """#38529: the Desktop bootstrap marker must be git-ignored so that
    ``jettstui update``'s ``git stash push --include-untracked`` does not sweep it
    into an autostash on every run.

    Behavioral + hermetic: build a throwaway repo that adopts the project's real
    ``.gitignore`` (the contract under test), drop the marker, and confirm the
    same stash invocation the updater uses leaves it untouched.
    """
    import shutil
    import subprocess

    if shutil.which("git") is None:
        pytest.skip("git not available")

    repo_gitignore = Path(jettstui_main.__file__).resolve().parents[1] / ".gitignore"

    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=tmp_path, capture_output=True, text=True, check=True
        )

    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (tmp_path / ".gitignore").write_text(repo_gitignore.read_text())
    (tmp_path / "tracked.txt").write_text("x\n")
    git("add", "-A")
    git("commit", "-qm", "init")

    marker = tmp_path / ".jettstui-bootstrap-complete"
    marker.write_text("")

    # Exact flags used by jettstui update (jettstui/main.py).
    git("stash", "push", "--include-untracked", "-m", "jettstui-update-autostash")

    assert marker.exists(), (
        ".jettstui-bootstrap-complete was swept into the update autostash — it must "
        "be listed in .gitignore so `git stash -u` skips it (#38529)."
    )
    # It must not even register as a dirty/untracked change.
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=tmp_path, capture_output=True, text=True
    ).stdout
    assert ".jettstui-bootstrap-complete" not in status


def test_install_method_marker_not_autostashed_by_update(tmp_path):
    """#66189: the installer ``.install_method`` stamp must be git-ignored so
    ``jettstui update``'s ``git stash push --include-untracked`` does not sweep it
    into an autostash on every run.

    ``scripts/install.sh`` writes ``$INSTALL_DIR/.install_method`` as runtime
    metadata; it is a sibling of ``.jettstui-bootstrap-complete`` /
    ``.update-incomplete`` and must be ignored the same way. Behavioral +
    hermetic: adopt the project's real ``.gitignore`` (the contract under test),
    drop the marker, and confirm the exact stash invocation the updater uses
    leaves it untouched.
    """
    import shutil
    import subprocess

    if shutil.which("git") is None:
        pytest.skip("git not available")

    repo_gitignore = Path(jettstui_main.__file__).resolve().parents[1] / ".gitignore"

    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=tmp_path, capture_output=True, text=True, check=True
        )

    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (tmp_path / ".gitignore").write_text(repo_gitignore.read_text())
    (tmp_path / "tracked.txt").write_text("x\n")
    git("add", "-A")
    git("commit", "-qm", "init")

    marker = tmp_path / ".install_method"
    marker.write_text("managed\n")

    # Exact flags used by jettstui update (jettstui/main.py).
    git("stash", "push", "--include-untracked", "-m", "jettstui-update-autostash")

    assert marker.exists(), (
        ".install_method was swept into the update autostash — it must be listed "
        "in .gitignore so `git stash -u` skips it (#66189)."
    )
    # It must not even register as a dirty/untracked change.
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=tmp_path, capture_output=True, text=True
    ).stdout
    assert ".install_method" not in status


# ---------------------------------------------------------------------------
# Permission-denied autostash class: undeletable untracked files (root-owned
# packaging/ etc.) must not abort the update when the stash entry was created.
# ---------------------------------------------------------------------------


def test_stash_push_partial_removal_failure_continues_when_stash_created(
    monkeypatch, tmp_path, capsys
):
    """git stash push exits 1 ("failed to remove ...: Permission denied") but
    the stash entry exists → treat as success, return the new ref."""
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if cmd[-2:] == ["status", "--porcelain"]:
            return SimpleNamespace(stdout=" M x.py\n?? packaging/\n", returncode=0)
        if cmd[-2:] == ["ls-files", "--unmerged"]:
            return SimpleNamespace(stdout="", returncode=0)
        if cmd[-3:] == ["rev-parse", "--verify", "refs/stash"]:
            # Before push: no stash. After push: new entry.
            probes = [c for c, _ in calls if c[-3:] == ["rev-parse", "--verify", "refs/stash"]]
            if len(probes) == 1:
                return SimpleNamespace(stdout="", returncode=1)
            return SimpleNamespace(stdout="newref123\n", returncode=0)
        if cmd[1:4] == ["stash", "push", "--include-untracked"]:
            return SimpleNamespace(
                stdout="Saved working directory and index state\n",
                stderr=(
                    "warning: failed to remove packaging/homebrew/jettstui.rb: "
                    "Permission denied\n"
                ),
                returncode=1,
            )
        if cmd[1:3] == ["reset", "--hard"]:
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(jettstui_main.subprocess, "run", fake_run)

    stash_ref = jettstui_main._stash_local_changes_if_needed(["git"], tmp_path)

    assert stash_ref == "newref123"
    # Tracked mods are saved in the stash but the failed push leaves them in
    # the tree — the follow-up reset must run so the checkout/pull can proceed.
    assert any(c[1:3] == ["reset", "--hard"] for c, _ in calls)
    out = capsys.readouterr().out
    assert "could not be removed" in out
    assert "update will continue" in out


def test_stash_push_failure_without_stash_entry_still_raises(monkeypatch, tmp_path, capsys):
    """git stash push fails AND no stash entry was created → real failure."""

    def fake_run(cmd, **kwargs):
        if cmd[-2:] == ["status", "--porcelain"]:
            return SimpleNamespace(stdout=" M x.py\n", returncode=0)
        if cmd[-2:] == ["ls-files", "--unmerged"]:
            return SimpleNamespace(stdout="", returncode=0)
        if cmd[-3:] == ["rev-parse", "--verify", "refs/stash"]:
            return SimpleNamespace(stdout="", returncode=1)
        if cmd[1:4] == ["stash", "push", "--include-untracked"]:
            return SimpleNamespace(
                stdout="", stderr="fatal: unable to write new index file\n",
                returncode=1, args=cmd,
            )
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(jettstui_main.subprocess, "run", fake_run)

    with pytest.raises(CalledProcessError):
        jettstui_main._stash_local_changes_if_needed(["git"], tmp_path)
    out = capsys.readouterr().out
    assert "update aborted" in out


def test_stash_push_failure_with_preexisting_stash_unchanged_still_raises(
    monkeypatch, tmp_path
):
    """A pre-existing stash entry must not be mistaken for a fresh save."""

    def fake_run(cmd, **kwargs):
        if cmd[-2:] == ["status", "--porcelain"]:
            return SimpleNamespace(stdout=" M x.py\n", returncode=0)
        if cmd[-2:] == ["ls-files", "--unmerged"]:
            return SimpleNamespace(stdout="", returncode=0)
        if cmd[-3:] == ["rev-parse", "--verify", "refs/stash"]:
            return SimpleNamespace(stdout="oldref456\n", returncode=0)
        if cmd[1:4] == ["stash", "push", "--include-untracked"]:
            return SimpleNamespace(stdout="", stderr="boom\n", returncode=1, args=cmd)
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(jettstui_main.subprocess, "run", fake_run)

    with pytest.raises(CalledProcessError):
        jettstui_main._stash_local_changes_if_needed(["git"], tmp_path)


def test_stash_apply_untracked_only_failure_detector():
    fn = jettstui_main._stash_apply_failed_only_on_existing_untracked
    assert fn(
        "packaging/homebrew/jettstui.rb already exists, no checkout\n"
        "error: could not restore untracked files from stash\n"
    ) is True
    # Tracked-apply failure lines must NOT be classified as benign.
    assert fn(
        "error: Your local changes to the following files would be overwritten by merge:\n"
        "\ttracked.txt\n"
        "Please commit your changes or stash them before you merge.\n"
        "Aborting\n"
        "packaging/homebrew/jettstui.rb already exists, no checkout\n"
        "error: could not restore untracked files from stash\n"
    ) is False
    assert fn("") is False
    assert fn("warning: something harmless\n") is False


def test_restore_treats_existing_untracked_only_failure_as_restored(
    monkeypatch, tmp_path, capsys
):
    """stash apply rc=1 purely from already-present untracked files → restored,
    stash dropped, no destructive reset."""
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if cmd[1:3] == ["status", "--porcelain"]:
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        if cmd[1:3] == ["stash", "apply"]:
            return SimpleNamespace(
                stdout="",
                stderr=(
                    "packaging/homebrew/jettstui.rb already exists, no checkout\n"
                    "error: could not restore untracked files from stash\n"
                ),
                returncode=1,
            )
        if cmd[1:3] == ["diff", "--name-only"]:
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        if cmd[1:3] == ["stash", "list"]:
            return SimpleNamespace(stdout="stash@{0} abc123\n", stderr="", returncode=0)
        if cmd[1:3] == ["stash", "drop"]:
            return SimpleNamespace(stdout="dropped\n", stderr="", returncode=0)
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(jettstui_main.subprocess, "run", fake_run)

    restored = jettstui_main._restore_stashed_changes(
        ["git"], tmp_path, "abc123", prompt_user=False
    )

    assert restored is True
    # No reset --hard in the command stream.
    assert not any("reset" in c for c, _ in calls)
    out = capsys.readouterr().out
    assert "kept as-is" in out
    assert "hit conflicts" not in out


def test_update_autostash_survives_undeletable_untracked_dir(tmp_path):
    """Behavioral E2E of the whole permission-denied class with real git:
    root-owned-style undeletable untracked dir → stash succeeds, update-style
    reset works, restore round-trips, nothing lost. (#70127 follow-up)"""
    import os
    import shutil
    import subprocess

    if shutil.which("git") is None:
        pytest.skip("git not available")
    if os.name == "nt":
        pytest.skip("POSIX permission semantics")
    if os.geteuid() == 0:
        pytest.skip("root ignores directory write bits")

    def git(*args, check=True):
        return subprocess.run(
            ["git", *args], cwd=tmp_path, capture_output=True, text=True, check=check
        )

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (tmp_path / "tracked.txt").write_text("v1\n")
    git("add", "-A")
    git("commit", "-qm", "init")

    (tmp_path / "tracked.txt").write_text("v2 local change\n")
    pkg = tmp_path / "packaging" / "homebrew"
    pkg.mkdir(parents=True)
    (pkg / "jettstui.rb").write_text("formula\n")
    os.chmod(pkg, 0o555)  # undeletable contents, like a root-owned dir
    try:
        stash_ref = jettstui_main._stash_local_changes_if_needed(["git"], tmp_path)
        assert stash_ref

        # The tracked change is stashed; simulate the updater's checkout window.
        assert (tmp_path / "tracked.txt").read_text() == "v1\n"

        restored = jettstui_main._restore_stashed_changes(
            ["git"], tmp_path, stash_ref, prompt_user=False
        )
        assert restored is True
        assert (tmp_path / "tracked.txt").read_text() == "v2 local change\n"
        assert (pkg / "jettstui.rb").read_text() == "formula\n"
    finally:
        os.chmod(pkg, 0o755)
