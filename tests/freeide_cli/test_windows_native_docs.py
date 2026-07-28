from pathlib import Path


def test_windows_native_install_path_docs_match_installer() -> None:
    doc = Path("website/docs/user-guide/windows-native.md").read_text()
    install = Path("scripts/install.ps1").read_text()

    assert "%LOCALAPPDATA%\\freeide\\freeide-agent\\venv\\Scripts" in doc
    assert "Get-Command freeide        # should print C:\\Users\\<you>\\AppData\\Local\\freeide\\freeide-agent\\venv\\Scripts\\freeide.exe" in doc
    assert '$freeideBin = "$InstallDir\\venv\\Scripts"' in install
