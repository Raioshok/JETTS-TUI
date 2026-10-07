"""Conflict-safe migration of the default Jetts-TUI data directory.

Explicit home overrides are not passed here: those may be user-managed profile
paths and must never be moved. A compatibility alias keeps older launchers and
installed runtimes pointing at the same data after a default-home rename.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def default_home_paths(*, platform: str, home: Path, local_appdata: str = "") -> tuple[Path, Path]:
    """Return (new default, old default) without touching either directory."""
    if platform == "win32":
        base = Path(local_appdata) if local_appdata.strip() else home / "AppData" / "Local"
        return base / "jettstui", base / "freeide"
    return home / ".jettstui", home / ".freeide"


def _create_compat_alias(old: Path, new: Path, *, platform: str) -> None:
    if platform != "win32":
        old.symlink_to(new, target_is_directory=True)
        return

    # Python's symlink API needs Developer Mode or an elevated token on many
    # Windows installations. Directory junctions do not. Keep cmd metacharacters
    # out of the only built-in Windows exposes for creating junctions.
    paths = (str(old), str(new))
    if any(char in path for path in paths for char in '&|<>^%!"\r\n'):
        raise ValueError("unsafe path for Windows junction creation")
    result = subprocess.run(
        ["cmd", "/d", "/c", "mklink", "/J", str(old), str(new)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=15,
    )
    if result.returncode != 0 or not old.is_dir():
        raise OSError(result.stderr.strip() or "junction creation failed")


def migrate_default_home(new: Path, old: Path, *, platform: str = sys.platform) -> Path:
    """Move one legacy default home only when destination is absent.

    Returns the usable path. On collision or failure, never merges or deletes
    either tree; on alias failure, attempts to roll back the rename. Callers
    should surface a warning if the returned path differs from ``new``.
    """
    if new.exists() or new.is_symlink():
        return new
    if not old.is_dir() or old.is_symlink():
        return new
    try:
        old.rename(new)
    except OSError:
        return old
    try:
        _create_compat_alias(old, new, platform=platform)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        # A half-migration would strand existing shortcuts and installers.
        if not old.exists() and not old.is_symlink():
            try:
                new.rename(old)
                return old
            except OSError:
                pass
        return new
    return new
