"""Resolve FREEIDE_HOME for standalone skill scripts.

Skill scripts may run outside the FreeIDE process (e.g. system Python,
nix env, CI) where ``freeide_constants`` is not importable.  This module
provides the same ``get_freeide_home()`` and ``display_freeide_home()``
contracts as ``freeide_constants`` without requiring it on ``sys.path``.

When ``freeide_constants`` IS available it is used directly so that any
future enhancements (profile resolution, Docker detection, etc.) are
picked up automatically.  The fallback path replicates the core logic
from ``freeide_constants.py`` using only the stdlib.

All scripts under ``google-workspace/scripts/`` should import from here
instead of duplicating the ``FREEIDE_HOME = Path(os.getenv(...))`` pattern.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from freeide_constants import display_freeide_home as display_freeide_home
    from freeide_constants import get_freeide_home as get_freeide_home
except (ModuleNotFoundError, ImportError):

    def get_freeide_home() -> Path:
        """Return the FreeIDE home directory (default: ~/.freeide).

        Mirrors ``freeide_constants.get_freeide_home()``."""
        val = os.environ.get("FREEIDE_HOME", "").strip()
        return Path(val) if val else Path.home() / ".freeide"

    def display_freeide_home() -> str:
        """Return a user-friendly ``~/``-shortened display string.

        Mirrors ``freeide_constants.display_freeide_home()``."""
        home = get_freeide_home()
        try:
            return "~/" + str(home.relative_to(Path.home()))
        except ValueError:
            return str(home)
