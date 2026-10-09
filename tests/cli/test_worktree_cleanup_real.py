"""Exercise the actual TUI worktree exit path against a disposable Git repo."""

from __future__ import annotations

import subprocess
from pathlib import Path

import cli
import pytest


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=cwd, text=True, encoding="utf-8",
        capture_output=True, check=True,
    )


def _worktree(tmp_path: Path) -> dict[str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "README.md").write_text("test\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial")
    # The cleanup path compares against remote-tracking refs. Keep the
    # disposable initial commit reachable without contacting a remote.
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    path = repo / "worktree"
    _git(repo, "worktree", "add", "-b", "test-cleanup", str(path))
    return {"path": str(path), "branch": "test-cleanup", "repo_root": str(repo)}


def test_exit_cleanup_preserves_uncommitted_work_and_branch(tmp_path: Path) -> None:
    info = _worktree(tmp_path)
    worktree = Path(info["path"])
    (worktree / "unsaved.txt").write_text("keep me", encoding="utf-8")

    cli._cleanup_worktree(info)

    assert (worktree / "unsaved.txt").read_text(encoding="utf-8") == "keep me"
    assert _git(Path(info["repo_root"]), "branch", "--list", info["branch"]).stdout.strip()


def test_exit_cleanup_removes_clean_worktree(tmp_path: Path) -> None:
    info = _worktree(tmp_path)

    cli._cleanup_worktree(info)

    assert not Path(info["path"]).exists()
    assert not _git(Path(info["repo_root"]), "branch", "--list", info["branch"]).stdout.strip()


def test_failed_worktree_removal_keeps_checkout_and_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    info = _worktree(tmp_path)
    original_run = subprocess.run

    def fail_remove(command, *args, **kwargs):
        if command[:3] == ["git", "worktree", "remove"]:
            return subprocess.CompletedProcess(command, 1, "", "simulated failure")
        return original_run(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", fail_remove)
    cli._cleanup_worktree(info)

    assert Path(info["path"]).exists()
    assert _git(Path(info["repo_root"]), "branch", "--list", info["branch"]).stdout.strip()


def test_orphan_pruner_preserves_unique_commits(tmp_path: Path) -> None:
    info = _worktree(tmp_path)
    cli._cleanup_worktree(info)
    repo = Path(info["repo_root"])
    main_branch = _git(repo, "branch", "--show-current").stdout.strip()
    branch = "jettstui/jettstui-unique"
    _git(repo, "checkout", "-b", branch)
    (repo / "work.txt").write_text("unmerged work", encoding="utf-8")
    _git(repo, "add", "work.txt")
    _git(repo, "commit", "-m", "unique work")
    _git(repo, "checkout", main_branch)

    cli._prune_orphaned_branches(str(repo))

    assert _git(repo, "branch", "--list", branch).stdout.strip()


def test_new_worktree_uses_jetts_identity(tmp_path: Path) -> None:
    initial = _worktree(tmp_path)
    repo = Path(initial["repo_root"])

    info = cli._setup_worktree(str(repo), sync_base=False)

    assert info is not None
    assert Path(info["path"]).name.startswith("jettstui-")
    assert info["branch"].startswith("jettstui/jettstui-")
    cli._cleanup_worktree(info)
