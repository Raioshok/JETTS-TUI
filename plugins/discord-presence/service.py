"""Background presence service: one worker thread, one Discord connection.

Agent hooks only mutate in-memory per-session state and poke the worker; they
never block on Discord. The worker reconnects with exponential backoff,
coalesces bursts of tool calls into at most one SET_ACTIVITY per
``MIN_UPDATE_INTERVAL`` (Discord allows ~5 updates per 20s), clears the
activity when idle or disabled, and clears it again on shutdown.

Sessions are tracked separately (the desktop backend runs many at once, each
in its own project) and folded into one card. Other JettsTUI processes share
their sessions through a :class:`~.peers.PeerRegistry`; only the lowest pid
with live work talks to Discord, so cards never fight.

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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from . import activity as act
from .ipc import DiscordIPC, DiscordIPCError, DiscordNotRunning
from .peers import HEARTBEAT, PeerRegistry

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
_DEFAULT_KEY = "default"


def _load_settings() -> act.PresenceSettings:
    try:
        from jettstui.config import load_config_readonly

        return act.PresenceSettings.from_config(load_config_readonly())
    except Exception as exc:  # config unreadable → stay off
        logger.debug("Discord presence: could not read config: %s", exc)
        return act.PresenceSettings()


def _project_name(cwd: str) -> str:
    """Name of the repo containing *cwd* (so ``repo/src`` is still ``repo``)."""
    try:
        path = Path(cwd).expanduser().resolve()
        home = Path.home().resolve()
    except (OSError, RuntimeError):
        return ""
    for candidate in (path, *list(path.parents)[:8]):
        if candidate == home or candidate.parent == candidate:
            break
        if (candidate / ".git").exists():
            return candidate.name
    return path.name


def _current_project(task_id: str = "") -> str:
    cwd = ""
    if task_id:
        # Desktop/TUI/ACP sessions each register their own workspace cwd.
        try:
            from tools.terminal_tool import resolve_task_overrides

            cwd = str(resolve_task_overrides(task_id).get("cwd") or "").strip()
        except Exception:
            cwd = ""
    cwd = cwd or (os.environ.get("TERMINAL_CWD") or "").strip() or os.getcwd()
    return _project_name(cwd)


def _default_registry() -> Optional[PeerRegistry]:
    try:
        from jettstui_constants import get_jettstui_home

        return PeerRegistry(get_jettstui_home() / "discord_presence" / "peers")
    except Exception as exc:
        logger.debug("Discord presence: no peer registry: %s", exc)
        return None


@dataclass
class _Session:
    phase: str = act.PHASE_IDLE
    tool: str = ""
    model: str = ""
    project: str = ""
    project_from_task: bool = False
    started_at: Optional[float] = None
    last_active_at: float = 0.0
    tool_calls: int = 0
    active_tools: Dict[str, str] = field(default_factory=dict)
    approvals: int = 0

    def view(self) -> act.Snapshot:
        return act.Snapshot(
            phase=self.phase,
            tool=self.tool,
            model=self.model,
            project=self.project,
            started_at=self.started_at,
            last_active_at=self.last_active_at,
            tool_calls=self.tool_calls,
        )


class PresenceService:
    def __init__(
        self,
        *,
        settings_loader: Callable[[], act.PresenceSettings] = _load_settings,
        ipc_factory: Callable[[str], DiscordIPC] = DiscordIPC,
        clock: Callable[[], float] = time.time,
        project_resolver: Callable[[str], str] = _current_project,
        monotonic: Callable[[], float] = time.monotonic,
        registry: Any = _default_registry,
        autostart: bool = True,
    ) -> None:
        self._settings_loader = settings_loader
        self._ipc_factory = ipc_factory
        self._clock = clock
        self._project_resolver = project_resolver
        self._monotonic = monotonic
        self._autostart = autostart
        self._registry: Optional[PeerRegistry] = registry() if callable(registry) else registry

        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._stopping = False
        self._thread: Optional[threading.Thread] = None

        self._sessions: Dict[str, _Session] = {}
        self._remote_sessions: Set[str] = set()
        self._peer_sessions: List[act.Snapshot] = []
        self._following: Optional[int] = None

        self._settings: Optional[act.PresenceSettings] = None
        self._settings_at = 0.0

        self._ipc: Optional[DiscordIPC] = None
        self._sent: Any = _UNSENT
        self._sent_at = 0.0
        self._omit_status_display = False
        self._last_error = ""
        self._backoff = BACKOFF_START
        self._next_connect_at = 0.0

    # ------------------------------------------------------------------ hooks

    def session_started(self, *, session_id: str = "", model: str = "", platform: str = "", task_id: str = "") -> None:
        if not self._accept(session_id, platform):
            return
        self._touch(session_id, task_id, model=model or None)

    def turn_started(self, *, session_id: str = "", model: str = "", platform: str = "", task_id: str = "") -> None:
        if not self._accept(session_id, platform):
            return
        self._touch(session_id, task_id, phase=act.PHASE_THINKING, model=model or None)

    def tool_started(self, *, session_id: str = "", tool_call_id: str = "", tool_name: str = "", task_id: str = "") -> None:
        if session_id in self._remote_sessions:
            return
        with self._lock:
            session = self._session(session_id)
            session.active_tools[tool_call_id or tool_name] = tool_name
            calls = session.tool_calls + 1
        self._touch(session_id, task_id, phase=act.PHASE_TOOL, tool=tool_name, tool_calls=calls)

    def tool_finished(self, *, session_id: str = "", tool_call_id: str = "", tool_name: str = "", task_id: str = "") -> None:
        if session_id in self._remote_sessions:
            return
        with self._lock:
            session = self._session(session_id)
            session.active_tools.pop(tool_call_id or tool_name, None)
            running = next(iter(session.active_tools.values()), "")
            waiting = session.approvals > 0
        if waiting:
            self._touch(session_id, task_id)
        elif running:
            self._touch(session_id, task_id, phase=act.PHASE_TOOL, tool=running)
        else:
            self._touch(session_id, task_id, phase=act.PHASE_THINKING, tool="")

    def approval_requested(self, *, session_id: str = "") -> None:
        with self._lock:
            key = self._approval_key(session_id)
            self._session(key).approvals += 1
        self._touch(key, "", phase=act.PHASE_APPROVAL)

    def approval_resolved(self, *, session_id: str = "") -> None:
        with self._lock:
            key = self._approval_key(session_id)
            session = self._session(key)
            session.approvals = max(0, session.approvals - 1)
            pending = session.approvals
            running = next(iter(session.active_tools.values()), "")
        if not pending:
            self._touch(key, "", phase=act.PHASE_TOOL if running else act.PHASE_THINKING, tool=running)

    def turn_finished(self, *, session_id: str = "") -> None:
        if session_id in self._remote_sessions:
            return
        with self._lock:
            session = self._session(session_id)
            session.active_tools.clear()
            session.approvals = 0
        self._touch(session_id, "", phase=act.PHASE_IDLE, tool="")

    def session_reset(self, *, session_id: str = "") -> None:
        """A conversation ended or restarted: forget it (or all, if unnamed)."""
        with self._lock:
            if session_id:
                self._sessions.pop(session_id, None)
                self._remote_sessions.discard(session_id)
            else:
                self._sessions.clear()
                self._remote_sessions.clear()
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

    def snapshot(self) -> act.Snapshot:
        """Everything live right now, here and in other processes, as one card."""
        settings = self.settings()
        now = self._clock()
        with self._lock:
            local = self._live_local(settings, now)
            peers = list(self._peer_sessions)
        return act.aggregate([*local, *peers])

    def status(self) -> Dict[str, Any]:
        settings = self.settings()
        snapshot = self.snapshot()
        with self._lock:
            ipc = self._ipc
            user = dict(ipc.user) if ipc is not None and ipc.connected else {}
            activity = None if self._sent is _UNSENT else self._sent
            following = self._following
        return {
            "enabled": settings.enabled,
            "configured": settings.configured,
            "running": self._thread is not None and self._thread.is_alive(),
            "connected": ipc is not None and ipc.connected,
            "user": _public_user(user),
            "error": self._last_error,
            "phase": snapshot.phase,
            "projects": list(snapshot.project_names) if settings.show_project else [],
            "project_count": len(snapshot.project_names),
            "shown_by_other_process": following is not None,
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
        if self._registry is not None:
            self._registry.withdraw()
        with self._lock:
            self._thread = None
            self._stopping = False

    # ------------------------------------------------------------- internals

    def _session(self, session_id: str) -> _Session:
        key = session_id or _DEFAULT_KEY
        session = self._sessions.get(key)
        if session is None:
            session = self._sessions[key] = _Session()
        return session

    def _approval_key(self, session_id: str) -> str:
        """Approval hooks carry a gateway session key, not always the agent's
        session id; fall back to the session that was just working."""
        if session_id and session_id in self._sessions:
            return session_id
        if not self._sessions:
            return session_id
        return max(self._sessions.items(), key=lambda item: item[1].last_active_at)[0]

    def _accept(self, session_id: str, platform: str) -> bool:
        local = (platform or "").strip().lower() in _LOCAL_PLATFORMS
        with self._lock:
            if session_id:
                if local:
                    self._remote_sessions.discard(session_id)
                else:
                    self._remote_sessions.add(session_id)
                    self._sessions.pop(session_id, None)
        return local

    def _touch(self, session_id: str, task_id: str, **changes: Any) -> None:
        now = self._clock()
        settings = self.settings()
        with self._lock:
            session = self._session(session_id)
            if task_id and not session.project_from_task:
                session.project = self._project_resolver(task_id) or session.project
                session.project_from_task = True
            elif not session.project:
                session.project = self._project_resolver("")
            expired = session.started_at is not None and act.is_idle_expired(settings, session.view(), now)
            if session.started_at is None or expired:
                # First activity, or first activity after presence went away.
                session.started_at = now
                if expired and "tool_calls" not in changes:
                    session.tool_calls = 0
            for key, value in changes.items():
                if value is not None:
                    setattr(session, key, value)
            session.last_active_at = now
        self._kick()

    def _live_local(self, settings: act.PresenceSettings, now: float) -> List[act.Snapshot]:
        """Sessions still worth showing; forgets the ones that timed out."""
        live: List[act.Snapshot] = []
        for key, session in list(self._sessions.items()):
            view = session.view()
            if not session.last_active_at:
                continue
            if act.is_idle_expired(settings, view, now):
                del self._sessions[key]
                continue
            live.append(view)
        return live

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
            project=snapshot.project or self._project_resolver(""),
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

    def _sync_peers(self, settings: act.PresenceSettings, now: float) -> Optional[int]:
        """Publish our sessions, read everyone else's, and return the pid that
        should own the Discord card when it isn't this process."""
        with self._lock:
            local = self._live_local(settings, now)
        registry = self._registry
        if registry is None:
            return None
        registry.publish(local, now)
        peers = registry.peers(now)
        with self._lock:
            self._peer_sessions = [session for _, sessions in peers for session in sessions]
        candidates = [pid for pid, _ in peers] + ([registry.pid] if local else [])
        owner = min(candidates) if candidates else registry.pid
        return None if owner == registry.pid else owner

    def _tick(self) -> Optional[float]:
        """One reconcile step: seconds to sleep before the next, or ``None``
        to let the worker exit (presence off; the next hook restarts it)."""
        settings = self.settings()
        if not settings.enabled or not settings.configured:
            self._shutdown_connection(clear=True)
            if self._registry is not None:
                self._registry.withdraw()
            self._last_error = "" if not settings.enabled else "Set a Discord Application ID to start presence"
            return None

        wall = self._clock()
        following = self._sync_peers(settings, wall)
        with self._lock:
            self._following = following
            shared = bool(self._peer_sessions) or bool(self._sessions)
        recheck = HEARTBEAT if shared else IDLE_RECHECK
        if following is not None:
            # Another process shows the combined card; stay off Discord.
            self._shutdown_connection(clear=True)
            self._last_error = ""
            return HEARTBEAT

        if self._ipc is not None and self._ipc.client_id != settings.client_id:
            self._shutdown_connection(clear=True)

        now = self._monotonic()
        if self._ipc is None:
            if now < self._next_connect_at:
                return min(recheck, self._next_connect_at - now)
            if not self._connect(settings.client_id):
                return max(0.5, min(recheck, self._next_connect_at - self._monotonic()))

        desired = act.compose_activity(settings, self.snapshot(), self._clock())
        if desired is not None and self._omit_status_display:
            desired.pop("status_display_type", None)
        if desired == self._sent:
            return recheck

        wait = self._sent_at + MIN_UPDATE_INTERVAL - self._monotonic()
        if wait > 0:
            return wait
        self._send(desired)
        return recheck if self._ipc is not None else BACKOFF_START

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
            self._omit_status_display = False
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
            if ipc.connected and activity and "status_display_type" in activity and not self._omit_status_display:
                # Older Discord clients reject the newer field; keep the card.
                self._omit_status_display = True
                activity = {k: v for k, v in activity.items() if k != "status_display_type"}
                self._send(activity)
                return
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
