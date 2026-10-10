"""`jettstui update` must find origin/<branch> on single-branch installer clones.

Installer checkouts come from ``git clone --depth 1 --branch X`` (single
branch). A bare ``git fetch origin main`` on such a clone only writes
FETCH_HEAD, so switching a ``codex/...`` install back to main failed with
"'origin/main' is not a commit". Exercised against real git repos.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from jettstui.main import _branch_fetch_refspec

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _git(cwd, *args):
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "init.defaultBranch=main", *args],
        cwd=cwd, capture_output=True, text=True, check=True,
    ).stdout.strip()


@pytest.fixture
def single_branch_clone(tmp_path):
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q")
    (origin / "a.txt").write_text("main\n")
    _git(origin, "add", ".")
    _git(origin, "commit", "-qm", "main")
    _git(origin, "checkout", "-qb", "feature")
    (origin / "a.txt").write_text("feature\n")
    _git(origin, "commit", "-qam", "feature")
    _git(origin, "checkout", "-q", "main")

    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", "--depth", "1", "--branch", "feature", f"file://{origin}", str(clone))
    return origin, clone


def test_bare_fetch_leaves_no_remote_tracking_ref(single_branch_clone):
    """Documents the failure mode the refspec guards against."""
    _origin, clone = single_branch_clone
    _git(clone, "fetch", "-q", "origin", "main")
    missing = subprocess.run(["git", "rev-parse", "--verify", "-q", "origin/main"], cwd=clone)
    assert missing.returncode != 0


def test_refspec_fetch_creates_remote_tracking_ref_and_branch_switch_works(single_branch_clone):
    origin, clone = single_branch_clone
    _git(clone, "fetch", "-q", "origin", _branch_fetch_refspec("origin", "main"))

    assert _git(clone, "rev-parse", "origin/main") == _git(origin, "rev-parse", "main")
    _git(clone, "checkout", "-qB", "main", "origin/main")
    assert (clone / "a.txt").read_text() == "main\n"


def test_update_fetch_creates_tracking_ref_without_touching_fetch_head(single_branch_clone, monkeypatch):
    """FETCH_HEAD is what a concurrent background fetch holds; the update must not need it."""
    import jettstui.main as jettstui_main

    origin, clone = single_branch_clone
    (clone / ".git" / "FETCH_HEAD").unlink(missing_ok=True)
    monkeypatch.setattr(jettstui_main, "PROJECT_ROOT", clone)

    result = jettstui_main._fetch_update_branch(["git"], "origin", "main")

    assert result.returncode == 0, result.stderr
    assert _git(clone, "rev-parse", "origin/main") == _git(origin, "rev-parse", "main")
    assert not (clone / ".git" / "FETCH_HEAD").exists()


def _scripted_run(monkeypatch, outcomes):
    """Patch subprocess.run in jettstui.main to return scripted fetch results."""
    import types

    import jettstui.main as jettstui_main

    calls = []

    def fake_run(cmd, **_kwargs):
        calls.append(cmd)
        code, stderr = outcomes[min(len(calls), len(outcomes)) - 1]
        return types.SimpleNamespace(returncode=code, stdout="", stderr=stderr)

    monkeypatch.setattr(jettstui_main.subprocess, "run", fake_run)
    monkeypatch.setattr(jettstui_main._time, "sleep", lambda _s: None)
    return jettstui_main, calls


def test_update_fetch_falls_back_when_git_lacks_no_write_fetch_head(monkeypatch):
    jettstui_main, calls = _scripted_run(monkeypatch, [
        (129, "error: unknown option `no-write-fetch-head'"),
        (0, ""),
    ])
    assert jettstui_main._fetch_update_branch(["git"], "origin", "main").returncode == 0
    assert "--no-write-fetch-head" in calls[0]
    assert "--no-write-fetch-head" not in calls[1]


def test_update_fetch_retries_once_when_another_git_holds_a_lock(monkeypatch):
    jettstui_main, calls = _scripted_run(monkeypatch, [
        (255, "error: cannot lock ref 'refs/remotes/origin/main': Unable to create '.git/refs/remotes/origin/main.lock'"),
        (0, ""),
    ])
    assert jettstui_main._fetch_update_branch(["git"], "origin", "main").returncode == 0
    assert len(calls) == 2
