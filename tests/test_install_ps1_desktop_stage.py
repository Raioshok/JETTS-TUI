"""install.ps1's desktop stage: opt-in for driver modes, never forced on them.

The Electron desktop's bootstrap-runner drives install.ps1 through
``-Manifest`` / ``-Stage`` from inside a running JettsTUI.exe; if those modes
gained the desktop stage, the rebuild would try to overwrite the live exe.
Runs the real script under PowerShell; skipped where none is installed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

INSTALL_PS1 = Path(__file__).resolve().parent.parent / "scripts" / "install.ps1"
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")

pytestmark = pytest.mark.skipif(POWERSHELL is None, reason="PowerShell not installed")


def _manifest_stages(*args: str) -> list[str]:
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-File", str(INSTALL_PS1), "-Manifest", *args],
        capture_output=True, text=True, timeout=120, check=True,
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    return [stage["name"] for stage in payload["stages"]]


def test_driver_manifest_leaves_the_desktop_build_out():
    assert "desktop" not in _manifest_stages()


def test_include_desktop_adds_the_stage_after_node_deps():
    stages = _manifest_stages("-IncludeDesktop")
    assert stages.index("desktop") == stages.index("node-deps") + 1
