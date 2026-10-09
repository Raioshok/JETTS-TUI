from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
SETUP_SCRIPT = REPO_ROOT / "setup-jetts-tui.sh"


def _bash_executable() -> str:
    # Windows can resolve `bash` to the WSL shim even when no distro is
    # installed. Git for Windows provides a shell that can validate this file.
    if sys.platform == "win32":
        git_bash = Path("C:/Program Files/Git/bin/bash.exe")
        if git_bash.is_file():
            return str(git_bash)
    return "bash"


def test_setup_jettstui_script_is_valid_shell():
    # A Windows-native absolute path is not meaningful to WSL/Git Bash.
    # Validate from the repository cwd so the same test works on every host.
    result = subprocess.run(
        [_bash_executable(), "-n", SETUP_SCRIPT.name],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_setup_jettstui_script_has_termux_path():
    content = SETUP_SCRIPT.read_text(encoding="utf-8")

    assert "is_termux()" in content
    assert ".[termux]" in content
    assert "constraints-termux.txt" in content
    assert "$PREFIX/bin" in content


def test_setup_jettstui_script_is_safe_to_rerun_and_noninteractive():
    content = SETUP_SCRIPT.read_text(encoding="utf-8")

    assert "--recreate" in content
    assert "Reusing existing venv" in content
    assert 'if [ -t 0 ]' in content
    assert "--skip-setup" in content
    assert 'SHELL_CONFIG="$HOME/.profile"' in content
    assert 'VENV_DIR="$SCRIPT_DIR/.venv"' in content
    assert 'from jettstui_constants import get_jettstui_home; print(get_jettstui_home() / "skills")' in content


def test_setup_jettstui_help_exits_before_installing():
    result = subprocess.run(
        [_bash_executable(), SETUP_SCRIPT.name, "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "--skip-setup" in result.stdout
    assert "--recreate" in result.stdout
