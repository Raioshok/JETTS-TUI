"""Share presence between JettsTUI processes on this machine.

Each process with live local sessions keeps a heartbeat file at
``<dir>/<pid>.json``. Every process can then see what the others are doing,
and exactly one of them — the lowest pid with live work — owns the Discord
connection and shows the combined card. A crashed process stops
heartbeating and drops out after ``PEER_TTL`` seconds.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from . import activity as act

HEARTBEAT = 15.0
PEER_TTL = 45.0

_FIELDS = ("phase", "tool", "model", "project", "started_at", "last_active_at", "tool_calls")


def _encode(session: act.Snapshot) -> Dict[str, object]:
    return {name: getattr(session, name) for name in _FIELDS}


def _decode(raw: object) -> Optional[act.Snapshot]:
    if not isinstance(raw, dict):
        return None
    try:
        started = raw.get("started_at")
        return act.Snapshot(
            phase=str(raw.get("phase") or act.PHASE_IDLE),
            tool=str(raw.get("tool") or ""),
            model=str(raw.get("model") or ""),
            project=str(raw.get("project") or ""),
            started_at=float(started) if started else None,
            last_active_at=float(raw.get("last_active_at") or 0.0),
            tool_calls=int(raw.get("tool_calls") or 0),
        )
    except (TypeError, ValueError):
        return None


class PeerRegistry:
    def __init__(self, directory: Path, pid: Optional[int] = None) -> None:
        self.directory = Path(directory)
        self.pid = os.getpid() if pid is None else pid
        self._path = self.directory / f"{self.pid}.json"
        self._written: Optional[Tuple[object, ...]] = None
        self._written_at = 0.0

    def publish(self, sessions: Sequence[act.Snapshot], now: float) -> None:
        """Advertise this process's live sessions; withdraw when there are none."""
        if not sessions:
            self.withdraw()
            return
        payload = [_encode(s) for s in sessions]
        key = tuple(json.dumps(item, sort_keys=True) for item in payload)
        if key == self._written and now - self._written_at < HEARTBEAT - 1:
            return
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.directory, prefix=f".{self.pid}-", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"pid": self.pid, "updated_at": now, "sessions": payload}, handle)
            os.replace(tmp, self._path)
        except OSError:
            return
        self._written = key
        self._written_at = now

    def withdraw(self) -> None:
        if self._written is None and not self._path.exists():
            return
        try:
            self._path.unlink()
        except OSError:
            pass
        self._written = None

    def peers(self, now: float) -> List[Tuple[int, List[act.Snapshot]]]:
        """Live sessions advertised by other processes; prunes stale files."""
        found: List[Tuple[int, List[act.Snapshot]]] = []
        try:
            entries = list(self.directory.glob("*.json"))
        except OSError:
            return found
        for path in entries:
            if path == self._path:
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                pid = int(data["pid"])
                updated = float(data["updated_at"])
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if now - updated > PEER_TTL:
                try:
                    path.unlink()
                except OSError:
                    pass
                continue
            sessions = [s for s in map(_decode, data.get("sessions") or []) if s is not None]
            if sessions:
                found.append((pid, sessions))
        return found
