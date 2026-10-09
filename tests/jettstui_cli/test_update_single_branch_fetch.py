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
