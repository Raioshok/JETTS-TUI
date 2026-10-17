"""Shared actions behind ``jettstui rpc``, ``/rpc`` and the desktop API."""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Tuple

from . import activity as act
from .ipc import DiscordIPC, DiscordIPCError
from .service import get_service, lookup_application

PLUGIN_NAME = "discord-presence"

# Settings the desktop tab may edit through update_settings().
_EDITABLE_BOOL = {"show_model", "show_project", "show_tool_activity", "show_elapsed", "phase_badges"}
_EDITABLE_TEXT = {"details", "state", "large_image", "large_text", "small_image", "small_text"}


def _save(key: str, value: Any) -> None:
    from jettstui.config_edit import save_config_value

    if not save_config_value(f"{act.CONFIG_SECTION}.{key}", value):
        raise OSError(f"Could not save {act.CONFIG_SECTION}.{key} to config.yaml")


def _ensure_plugin_enabled() -> None:
    """Add the plugin to ``plugins.enabled`` and load it into this process."""
    from jettstui import plugins_cmd

    enabled = plugins_cmd._get_enabled_set()
    disabled = plugins_cmd._get_disabled_set()
    if PLUGIN_NAME not in enabled or PLUGIN_NAME in disabled:
        enabled.add(PLUGIN_NAME)
        disabled.discard(PLUGIN_NAME)
        plugins_cmd._save_enabled_set(enabled)
        plugins_cmd._save_disabled_set(disabled)

    from jettstui.plugins import discover_plugins, get_plugin_manager

    loaded = any(
        p.get("name") == PLUGIN_NAME and p.get("enabled") for p in get_plugin_manager().list_plugins()
    )
    if not loaded:
        # A long-lived backend (desktop, dashboard) discovered plugins before
        # this one was enabled; rescan so its hooks start firing now.
        discover_plugins(force=True)


def set_enabled(enabled: bool) -> Dict[str, Any]:
    if enabled:
        _ensure_plugin_enabled()
    _save("enabled", bool(enabled))
    service = get_service()
    service.refresh()
    return service.status()


def set_client_id(client_id: str) -> Dict[str, Any]:
    """Validate an Application ID against Discord and store it."""
    app = lookup_application(client_id)
    _save("client_id", app["id"])
    get_service().refresh()
    return app


def set_preset(name: str) -> str:
    preset = act.resolve_preset(name)
    if name not in act.PRESETS and name not in act.PRESET_ALIASES:
        raise ValueError(f"Unknown preset '{name}'. Choose one of: {', '.join(act.PRESETS)}")
    _save("preset", preset)
    get_service().refresh()
    return preset


def update_settings(changes: Dict[str, Any]) -> Dict[str, Any]:
    """Apply a validated partial update from the desktop settings tab."""
    for key, value in changes.items():
        if key in _EDITABLE_BOOL:
            _save(key, bool(value))
        elif key in _EDITABLE_TEXT:
            if not isinstance(value, str):
                raise ValueError(f"{key} must be text")
            text = value.strip()
            if key.endswith("_image") and text and not (text.startswith("https://") or re.fullmatch(r"[\w.-]{1,256}", text)):
                raise ValueError(f"{key} must be an https:// URL or an art asset key from your Discord app")
            _save(key, text[: act.MAX_TEXT] if not key.endswith("_image") else text)
        elif key == "preset":
            set_preset(str(value))
        elif key == "status_display":
            if value not in act.STATUS_DISPLAY_TYPES:
                raise ValueError(f"status_display must be one of: {', '.join(act.STATUS_DISPLAY_TYPES)}")
            _save(key, value)
        elif key == "activity_type":
            if value not in act.ACTIVITY_TYPES:
                raise ValueError(f"activity_type must be one of: {', '.join(act.ACTIVITY_TYPES)}")
            _save(key, value)
        elif key == "idle_timeout_minutes":
            minutes = int(value)
            if not 0 <= minutes <= 24 * 60:
                raise ValueError("idle_timeout_minutes must be between 0 and 1440")
            _save(key, minutes)
        elif key == "buttons":
            if not isinstance(value, list):
                raise ValueError("buttons must be a list")
            buttons: List[Dict[str, str]] = []
            for item in value[: act.MAX_BUTTONS]:
                button = act.valid_button((item or {}).get("label"), (item or {}).get("url"))
                if button is None:
                    raise ValueError("Each button needs a label and an https:// URL")
                buttons.append({"label": button[0], "url": button[1]})
            _save(key, buttons)
        else:
            raise ValueError(f"Unknown setting '{key}'")
    service = get_service()
    service.refresh()
    return service.status()


def send_test(seconds: float = 15.0, *, sleep=time.sleep) -> Dict[str, Any]:
    """Show the preview card for ``seconds`` on a separate connection.

    Used by the CLI, where the presence service is not running in the same
    process. In-process callers should prefer :func:`get_service` state.
    """
    service = get_service()
    settings = service.settings(fresh=True)
    if not settings.configured:
        raise ValueError("Set a Discord Application ID first (jettstui rpc setup <id>)")
    preview = service.status()["preview"]
    ipc = DiscordIPC(settings.client_id)
    user = ipc.connect()
    try:
        ipc.set_activity(preview)
        sleep(max(0.0, seconds))
        ipc.set_activity(None)
    finally:
        ipc.close()
    return {"user": user, "activity": preview}


def probe(client_id: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """Handshake with Discord (no activity change): ``(user, error)``."""
    ipc = DiscordIPC(client_id)
    try:
        return ipc.connect(timeout=3.0), ""
    except DiscordIPCError as exc:
        return None, str(exc)
    finally:
        ipc.close()


def format_status(status: Dict[str, Any], *, user: Optional[Dict[str, Any]] = None, error: str = "") -> str:
    settings = status["settings"]
    user = user if user is not None else status.get("user") or {}
    error = error or status.get("error") or ""
    lines = ["Discord Presence"]
    lines.append(f"  Enabled:     {'yes' if status['enabled'] else 'no'}")
    lines.append(f"  App ID:      {settings['client_id'] or '(not set — run: jettstui rpc setup <application-id>)'}")
    if user:
        name = user.get("display_name") or user.get("global_name") or user.get("username") or "?"
        lines.append(f"  Discord:     connected as {name}")
    elif status.get("shown_by_other_process"):
        lines.append("  Discord:     shown by another JettsTUI window")
    elif error:
        lines.append(f"  Discord:     {error}")
    else:
        lines.append("  Discord:     not connected")
    count = status.get("project_count") or 0
    if count:
        names = ", ".join(status.get("projects") or [])
        lines.append(f"  Projects:    {count}{f' ({names})' if names else ''}")
    lines.append(f"  Preset:      {settings['preset']}")
    shown = [label for key, label in (
        ("show_model", "model"),
        ("show_project", "project"),
        ("show_tool_activity", "activity"),
        ("show_elapsed", "timer"),
    ) if settings[key]]
    lines.append(f"  Shares:      {', '.join(shown) or 'nothing beyond the preset text'}")
    preview = status.get("preview") or {}
    if preview:
        lines.append("  Preview:")
        for key in ("details", "state"):
            if preview.get(key):
                lines.append(f"    {preview[key]}")
    return "\n".join(lines)
