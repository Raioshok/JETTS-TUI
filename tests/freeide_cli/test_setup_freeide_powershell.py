from pathlib import Path
import shutil
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SETUP_SCRIPT = REPO_ROOT / "setup-jetts-tui.ps1"


def test_windows_setup_script_has_expected_safe_rerun_contract():
    content = SETUP_SCRIPT.read_text(encoding="utf-8")

    assert "[switch]$SkipSetup" in content
    assert "[switch]$Recreate" in content
    assert "Reusing existing venv" in content
    assert 'Join-Path $RepoRoot ".venv"' in content
    assert "scripts\\install.ps1" in content
    assert "powershell.exe -NoProfile -ExecutionPolicy Bypass" in content
    assert '-Ensure "node"' in content
    assert "tools\\skills_sync.py" in content


def test_windows_setup_script_parses_when_powershell_is_available():
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell is not installed on this test host")

    path = str(SETUP_SCRIPT).replace("'", "''")
    command = (
        "$errors = $null; $tokens = $null; "
        f"[void][System.Management.Automation.Language.Parser]::ParseFile('{path}', "
        "[ref]$tokens, [ref]$errors); "
        "if ($errors.Count) { $errors | ForEach-Object { Write-Error $_.Message }; exit 1 }"
    )
    result = subprocess.run(
        [shell, "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
