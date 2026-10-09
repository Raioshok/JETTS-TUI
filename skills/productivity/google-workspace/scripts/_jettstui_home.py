"""Resolve JETTSTUI_HOME for standalone skill scripts.

Skill scripts may run outside the JettsTUI process (e.g. system Python,
nix env, CI) where ``jettstui_constants`` is not importable.  This module
provides the same ``get_jettstui_home()`` and ``display_jettstui_home()``
contracts as ``jettstui_constants`` without requiring it on ``sys.path``.

When ``jettstui_constants`` IS available it is used directly so that any
future enhancements (profile resolution, Docker detection, etc.) are
picked up automatically.  The fallback path replicates the core logic
from ``jettstui_constants.py`` using only the stdlib.

All scripts under ``google-workspace/scripts/`` should import from here
instead of duplicating the ``JETTSTUI_HOME = Path(os.getenv(...))`` pattern.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from jettstui_constants import display_jettstui_home as display_jettstui_home
    from jettstui_constants import get_jettstui_home as get_jettstui_home
except (ModuleNotFoundError, ImportError):

    def get_jettstui_home() -> Path:
        """Return the JettsTUI home directory (default: ~/.jettstui).

        Mirrors ``jettstui_constants.get_jettstui_home()``."""
        val = os.environ.get("JETTSTUI_HOME", "").strip()
        return Path(val) if val else Path.home() / ".jettstui"

    def display_jettstui_home() -> str:
        """Return a user-friendly ``~/``-shortened display string.

        Mirrors ``jettstui_constants.display_jettstui_home()``."""
        home = get_jettstui_home()
        try:
            return "~/" + str(home.relative_to(Path.home()))
        except ValueError:
            return str(home)
