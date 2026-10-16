"""Background presence service: one worker thread, one Discord connection.

Agent hooks only mutate an in-memory snapshot and poke the worker; they never
block on Discord. The worker reconnects with exponential backoff, coalesces
bursts of tool calls into at most one SET_ACTIVITY per ``MIN_UPDATE_INTERVAL``
(Discord allows ~5 updates per 20s), clears the activity when idle or
disabled, and clears it again on shutdown.

This module holds the process-wide singleton. It is imported both by the
plugin entry point and by the dashboard API module; keep the state here so
both share it.
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Set

from . import activity as act
from .ipc import DiscordIPC, DiscordIPCError, DiscordNotRunning

logger = logging.getLogger(__name__)

MIN_UPDATE_INTERVAL = 4.0
SETTINGS_TTL = 2.0
BACKOFF_START = 2.0
BACKOFF_MAX = 60.0
IDLE_RECHECK = 30.0

# Turns from messaging platforms run headless on a server; broadcasting them
# as the host user's Discord activity would be wrong.
_LOCAL_PLATFORMS = {"", "cli", "tui", "desktop", "dashboard", "acp", "local"}

_UNSENT = object()  # nothing sent on the current connection yet


def _load_settings() -> act.PresenceSettings:
    try:
        from jettstui.config import load_config_readonly

        return act.PresenceSettings.from_config(load_config_readonly())
    except Exception as exc:  # config unreadable → stay off
        logger.debug("Discord presence: could not read config: %s", exc)
        return act.PresenceSettings()


def _current_project() -> str:
    cwd = (os.environ.get("TERMINAL_CWD") or "").strip() or os.getcwd()
    try:
        return Path(cwd).expanduser().resolve().name
    except OSError:
        return ""


class PresenceService:
    def __init__(
        self,
        *,
        settings_loader: Callable[[], act.PresenceSettings] = _load_settings,
        ipc_factory: Callable[[str], DiscordIPC] = DiscordIPC,
        clock: Callable[[], float] = time.time,
        project_resolver: Callable[[], str] = _current_project,
        monotonic: Callable[[], float] = time.monotonic,
        autostart: bool = True,
    ) -> None:
        self._settings_loader = settings_loader
        self._ipc_factory = ipc_factory
        self._clock = clock
        self._project_resolver = project_resolver
        self._monotonic = monotonic
        self._autostart = autostart

        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._stopping = False
        self._thread: Optional[threading.Thread] = None

        self._snapshot = act.Snapshot()
        self._active_tools: Dict[str, str] = {}
        self._remote_sessions: Set[str] = set()
        self._approvals = 0

        self._settings: Optional[act.PresenceSettings] = None
        self._settings_at = 0.0

        self._ipc: Optional[DiscordIPC] = None
        self._sent: Any = _UNSENT
        self._sent_at = 0.0
        self._last_error = ""
        self._backoff = BACKOFF_START
        self._next_connect_at = 0.0

    # ------------------------------------------------------------------ hooks

    def session_started(self, *, session_id: str = "", model: str = "", platform: str = "") -> None:
        if not self._accept(session_id, platform):
            return
        self._update(model=model or None)

    def turn_started(self, *, session_id: str = "", model: str = "", platform: str = "") -> None:
        if not self._accept(session_id, platform):
            return
        self._update(phase=act.PHASE_THINKING, model=model or None)

    def tool_started(self, *, session_id: str = "", tool_call_id: str = "", tool_name: str = "") -> None:
        if session_id in self._remote_sessions:
            return
        with self._lock:
            self._active_tools[tool_call_id or tool_name] = tool_name
            calls = self._snapshot.tool_calls + 1
        self._update(phase=act.PHASE_TOOL, tool=tool_name, tool_calls=calls)

    def tool_finished(self, *, session_id: str = "", tool_call_id: str = "", tool_name: str = "") -> None:
        if session_id in self._remote_sessions:
            return
        with self._lock:
            self._active_tools.pop(tool_call_id or tool_name, None)
            running = next(iter(self._active_tools.values()), "")
        if running:
            self._update(phase=act.PHASE_TOOL, tool=running)
        else:
            self._update(phase=act.PHASE_THINKING, tool="")

    def approval_requested(self) -> None:
        with self._lock:
            self._approvals += 1
        self._update(phase=act.PHASE_APPROVAL)

    def approval_resolved(self) -> None:
        with self._lock:
            self._approvals = max(0, self._approvals - 1)
            pending = self._approvals
            running = next(iter(self._active_tools.values()), "")
        if not pending:
            self._update(phase=act.PHASE_TOOL if running else act.PHASE_THINKING, tool=running)

    def turn_finished(self, *, session_id: str = "") -> None:
        if session_id in self._remote_sessions:
            return
        with self._lock:
            self._active_tools.clear()
            self._approvals = 0
        self._update(phase=act.PHASE_IDLE, tool="")

    def session_reset(self) -> None:
        """A new conversation: restart the elapsed timer and counters."""
        with self._lock:
            self._active_tools.clear()
            self._approvals = 0
            self._snapshot = self._snapshot.with_(
                phase=act.PHASE_IDLE, tool="", started_at=None, tool_calls=0, last_active_at=self._clock()
            )
        self._kick()

    # --------------------------------------------------------------- control

    def settings(self, *, fresh: bool = False) -> act.PresenceSettings:
        now = self._monotonic()
        with self._lock:
            if fresh or self._settings is None or now - self._settings_at >= SETTINGS_TTL:
                self._settings = self._settings_loader()
                self._settings_at = now
            return self._settings

    def refresh(self) -> None:
        """Re-read config now (after a settings change) and re-sync Discord."""
        settings = self.settings(fresh=True)
        with self._lock:
            self._next_connect_at = 0.0
            self._backoff = BACKOFF_START
        if settings.enabled or self._ipc is not None:
            self._kick()

    def status(self) -> Dict[str, Any]:
        settings = self.settings()
        with self._lock:
            ipc = self._ipc
            user = dict(ipc.user) if ipc is not None and ipc.connected else {}
            snapshot = self._snapshot
            activity = None if self._sent is _UNSENT else self._sent
            return {
                "enabled": settings.enabled,
                "configured": settings.configured,
                "running": self._thread is not None and self._thread.is_alive(),
                "connected": ipc is not None and ipc.connected,
                "user": _public_user(user),
                "error": self._last_error,
                "phase": snapshot.phase,
                "activity": activity,
                "preview": act.compose_activity(settings, self._preview_snapshot(snapshot), self._clock()),
                "settings": settings.to_public(),
                "presets": [{"id": key, "label": value["label"]} for key, value in act.PRESETS.items()],
            }

    def stop(self, timeout: float = 2.0) -> None:
        with self._lock:
            self._stopping = True
            thread = self._thread
        self._wake.set()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout)
        with self._lock:
            self._thread = None
            self._stopping = False

    # ------------------------------------------------------------- internals

    def _accept(self, session_id: str, platform: str) -> bool:
        local = (platform or "").strip().lower() in _LOCAL_PLATFORMS
        with self._lock:
            if session_id:
                if local:
                    self._remote_sessions.discard(session_id)
                else:
                    self._remote_sessions.add(session_id)
        return local

    def _update(self, **changes: Any) -> None:
        now = self._clock()
        with self._lock:
            changes = {key: value for key, value in changes.items() if value is not None}
            snapshot = self._snapshot
            if snapshot.started_at is None or act.is_idle_expired(self.settings(), snapshot, now):
                # First activity, or first activity after presence went away.
                changes.setdefault("started_at", now)
                if act.is_idle_expired(self.settings(), snapshot, now):
                    changes.setdefault("tool_calls", 0)
            if not snapshot.project:
                changes.setdefault("project", self._project_resolver())
            changes["last_active_at"] = now
            self._snapshot = snapshot.with_(**changes)
        self._kick()

    def _kick(self) -> None:
        if not self.settings().enabled and self._ipc is None:
            return
        with self._lock:
            if self._stopping:
                return
            self._wake.set()
            if not self._autostart:
                return
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="discord-presence", daemon=True)
                self._thread.start()

    def _preview_snapshot(self, snapshot: act.Snapshot) -> act.Snapshot:
        """What the card would show while working, for the settings preview."""
        now = self._clock()
        return snapshot.with_(
            phase=act.PHASE_TOOL if snapshot.phase == act.PHASE_IDLE else snapshot.phase,
            tool=snapshot.tool or "patch",
            model=snapshot.model or "your-model",
            project=snapshot.project or self._project_resolver(),
            started_at=snapshot.started_at or now,
            last_active_at=now,
            tool_calls=snapshot.tool_calls or 3,
        )

    def _run(self) -> None:
        try:
            while True:
                with self._lock:
                    if self._stopping:
                        break
                self._wake.clear()
                delay = self._tick()
                if delay is None:
                    # Exit under the lock so a concurrent _kick either sees a
                    # dead thread (and starts a new one) or its wake is seen here.
                    with self._lock:
                        if not self._wake.is_set():
                            self._thread = None
                            break
                    continue
                self._wake.wait(delay)
        finally:
            self._shutdown_connection(clear=True)

    def _tick(self) -> Optional[float]:
        """One reconcile step: seconds to sleep before the next, or ``None``
        to let the worker exit (presence off; the next hook restarts it)."""
        settings = self.settings()
        if not settings.enabled or not settings.configured:
            self._shutdown_connection(clear=True)
            self._last_error = "" if not settings.enabled else "Set a Discord Application ID to start presence"
            return None

        if self._ipc is not None and self._ipc.client_id != settings.client_id:
            self._shutdown_connection(clear=True)

        now = self._monotonic()
        if self._ipc is None:
            if now < self._next_connect_at:
                return self._next_connect_at - now
            if not self._connect(settings.client_id):
                return max(0.5, self._next_connect_at - self._monotonic())

        with self._lock:
            snapshot = self._snapshot
        desired = act.compose_activity(settings, snapshot, self._clock())
        if desired == self._sent:
            return IDLE_RECHECK

        wait = self._sent_at + MIN_UPDATE_INTERVAL - self._monotonic()
        if wait > 0:
            return wait
        self._send(desired)
        return IDLE_RECHECK if self._ipc is not None else BACKOFF_START

    def _connect(self, client_id: str) -> bool:
        ipc = self._ipc_factory(client_id)
        try:
            ipc.connect()
        except DiscordIPCError as exc:
            self._last_error = str(exc)
            # A rejected Application ID will not fix itself on retry.
            backoff = BACKOFF_MAX if not isinstance(exc, DiscordNotRunning) and exc.code else self._backoff
            self._next_connect_at = self._monotonic() + backoff
            self._backoff = min(BACKOFF_MAX, self._backoff * 2)
            logger.debug("Discord presence: connect failed: %s", exc)
            return False
        with self._lock:
            self._ipc = ipc
            self._sent = _UNSENT
            self._sent_at = 0.0
        self._last_error = ""
        self._backoff = BACKOFF_START
        logger.info("Discord presence connected as %s", _public_user(ipc.user).get("username", "?"))
        return True

    def _send(self, activity: Optional[Dict[str, Any]]) -> None:
        ipc = self._ipc
        if ipc is None:
            return
        try:
            ipc.set_activity(activity)
        except DiscordIPCError as exc:
            self._last_error = str(exc)
            logger.debug("Discord presence: update failed: %s", exc)
            if not ipc.connected:
                with self._lock:
                    self._ipc = None
                self._next_connect_at = self._monotonic() + self._backoff
            else:
                # Discord rejected the payload itself; don't resend it in a loop.
                self._sent = activity
            self._sent_at = self._monotonic()
            return
        with self._lock:
            self._sent = activity
            self._sent_at = self._monotonic()
        self._last_error = ""

    def _shutdown_connection(self, *, clear: bool) -> None:
        with self._lock:
            ipc, self._ipc = self._ipc, None
            self._sent = _UNSENT
        if ipc is None:
            return
        if clear and ipc.connected:
            try:
                ipc.set_activity(None)
            except DiscordIPCError:
                pass
        ipc.close()


def _public_user(user: Dict[str, Any]) -> Dict[str, Any]:
    if not user:
        return {}
    name = str(user.get("global_name") or user.get("username") or "")
    return {"id": str(user.get("id") or ""), "username": str(user.get("username") or ""), "display_name": name}


def lookup_application(client_id: str, *, timeout: float = 6.0) -> Dict[str, Any]:
    """Resolve a Discord Application ID via Discord's public RPC endpoint.

    Raises ``ValueError`` for malformed or unknown IDs, ``OSError`` when
    Discord cannot be reached.
    """
    app_id = act.normalize_client_id(client_id)
    if not app_id:
        raise ValueError("An Application ID is the 17–20 digit number from the Discord Developer Portal")
    request = urllib.request.Request(
        f"https://discord.com/api/v10/applications/{app_id}/rpc",
        headers={"Accept": "application/json", "User-Agent": "JettsTUI-DiscordPresence"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https host
            data = json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        if exc.code in (400, 404):
            raise ValueError(f"Discord has no application with ID {app_id}") from exc
        raise OSError(f"Discord returned HTTP {exc.code}") from exc
    icon = data.get("icon")
    return {
        "id": str(data.get("id") or app_id),
        "name": str(data.get("name") or ""),
        "icon_url": f"https://cdn.discordapp.com/app-icons/{app_id}/{icon}.png?size=128" if icon else "",
    }


_service: Optional[PresenceService] = None
_service_lock = threading.Lock()


def get_service() -> PresenceService:
    global _service
    with _service_lock:
        if _service is None:
            _service = PresenceService()
            atexit.register(_service.stop)
        return _service
