"""`jettstui update` converts a git-less install tree into a checkout."""

import shutil
import subprocess
from pathlib import Path

import pytest

from jettstui import main as jmain

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
        stdin=subprocess.DEVNULL,
    ).stdout.strip()


@pytest.fixture
def origin(tmp_path, monkeypatch):
    src = tmp_path / "origin"
    (src / "jettstui").mkdir(parents=True)
    (src / "jettstui" / "main.py").write_text("NEW = True\n")
    (src / "README.md").write_text("upstream\n")
    _git(src, "init", "-q", "-b", "main")
    _git(src, "-c", "user.name=t", "-c", "user.email=t@t", "add", ".")
    _git(src, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init")
    monkeypatch.setattr(jmain, "OFFICIAL_REPO_URL", src.as_uri())
    return src


def _gitless_install(tmp_path: Path) -> Path:
    root = tmp_path / "install"
    (root / "jettstui").mkdir(parents=True)
    (root / "jettstui" / "main.py").write_text("OLD = True\n")
    (root / "venv").mkdir()
    (root / "venv" / "marker").write_text("keep me\n")
    return root


def test_adopt_checks_out_upstream_and_keeps_untracked(origin, tmp_path):
    root = _gitless_install(tmp_path)

    assert jmain._adopt_non_git_install(["git"], root, "main") is True

    assert (root / "jettstui" / "main.py").read_text() == "NEW = True\n"
    assert (root / "README.md").read_text() == "upstream\n"
    assert (root / "venv" / "marker").read_text() == "keep me\n"
    assert _git(root, "rev-parse", "HEAD") == _git(origin, "rev-parse", "HEAD")
    assert _git(root, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert _git(root, "rev-parse", "--abbrev-ref", "@{upstream}") == "origin/main"


def test_adopt_failure_leaves_tree_untouched(origin, tmp_path):
    root = _gitless_install(tmp_path)

    assert jmain._adopt_non_git_install(["git"], root, "no-such-branch") is False

    assert not (root / ".git").exists()
    assert (root / "jettstui" / "main.py").read_text() == "OLD = True\n"
    assert (root / "venv" / "marker").read_text() == "keep me\n"
