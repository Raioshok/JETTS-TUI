from pathlib import Path


def test_windows_native_install_path_docs_match_installer() -> None:
    doc = Path("docs/user-guide/windows-native.md").read_text()
    install = Path("scripts/install.ps1").read_text()

    assert "%LOCALAPPDATA%\\jettstui\\jettstui\\venv\\Scripts" in doc
    assert "Get-Command jettstui        # should print C:\\Users\\<you>\\AppData\\Local\\jettstui\\jettstui\\venv\\Scripts\\jettstui.exe" in doc
    assert '$jettstuiBin = "$InstallDir\\venv\\Scripts"' in install
