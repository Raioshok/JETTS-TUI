"""Targeted configuration edits shared by the TUI gateway and legacy commands.

Keep this import-light: the gateway must not import the interactive console to
persist one setting. Writes always target the user's active home, including on
first run, so an installed package or checkout is never modified by a setting.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from jettstui_constants import get_jettstui_home


logger = logging.getLogger(__name__)


def save_config_value(key_path: str, value: Any, *, home: Path | None = None) -> bool:
    """Atomically edit one dotted config key without rewriting sibling keys."""
    config_path = (home if home is not None else get_jettstui_home()) / "config.yaml"

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        from utils import atomic_roundtrip_yaml_update

        atomic_roundtrip_yaml_update(config_path, key_path, value)
        try:
            os.chmod(config_path, 0o600)
        except (OSError, NotImplementedError):
            pass
        return True
    except Exception:
        logger.exception("Failed to save config key %s", key_path)
        return False
