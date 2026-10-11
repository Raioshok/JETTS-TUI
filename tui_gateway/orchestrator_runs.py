"""Headless orchestrator flows for the desktop Orchestrator tab.

The Orchestrator tab runs a flow (``agent/orchestrator.py``) without a chat: a
hidden *coordinator* agent — never run itself, it only lends its credentials,
tools and identity to the flow's subagents — has its progress callback pointed
at a recorder here. The recorder keeps the flow's ``orchestrator.run`` /
``orchestrator.stage`` events (the desktop replays them with the same reducers
the Flow sidebar uses) and a short live log per subagent. Nothing is persisted
as a session, so flows never show up in the session list.

One running flow per workspace: each flow already runs four agents at once.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional

_MAX_EVENTS = 600
_MAX_SUBAGENT_LINES = 24
_MAX_FINISHED = 20

CoordinatorFactory = Callable[["OrchestratorRun"], Any]
"""run -> an AIAgent-like coordinator whose tool_progress_callback we own."""

FlowRunner = Callable[[Any, str], dict]
"""(coordinator, task) -> the flow report (``agent.orchestrator.run_flow``)."""


@dataclass
class OrchestratorRun:
    id: str
    cwd: str
    task: str
    status: str = "running"  # running | approved | changes_requested | failed | interrupted
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    events: Deque[dict] = field(default_factory=lambda: deque(maxlen=_MAX_EVENTS))
    subagents: Dict[str, dict] = field(default_factory=dict)
    report: Optional[dict] = None
    error: str = ""
    coordinator: Any = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    # ── recording (called from the flow's worker threads) ─────────────────

    def record(self, event_type: str, name: Optional[str] = None, preview: Optional[str] = None,
               _args: Any = None, **kwargs: Any) -> None:
        if event_type in ("orchestrator.run", "orchestrator.stage"):
            flow = kwargs.get("flow")
            if isinstance(flow, dict):
                with self.lock:
                    self.events.append({"type": event_type, "payload": dict(flow), "at": time.time()})
            return
        if event_type.startswith("subagent."):
            self._record_subagent(event_type, name, preview, kwargs)

    def _record_subagent(self, event_type: str, name: Optional[str], preview: Optional[str], kw: dict) -> None:
        sid = str(kw.get("subagent_id") or "")
        if not sid or event_type == "subagent.text":
            return
        with self.lock:
            row = self.subagents.setdefault(
                sid, {"id": sid, "model": "", "status": "running", "current_tool": "", "stream": []}
            )
            if kw.get("model"):
                row["model"] = str(kw["model"])
            if kw.get("child_session_id"):
                row["session_id"] = str(kw["child_session_id"])
            if kw.get("status"):
                row["status"] = str(kw["status"])
            if event_type == "subagent.complete":
                row["status"] = str(kw.get("status") or "completed")
                row["current_tool"] = ""
            line = ""
            if name:
                row["current_tool"] = str(name)
                line = f"{name}  {preview}".strip() if preview else str(name)
            elif event_type in ("subagent.progress", "subagent.thinking") and preview:
                line = str(preview)
            if line:
                line = " ".join(line.split())[:220]
                stream = row["stream"]
                if not stream or stream[-1]["text"] != line:
                    stream.append({"at": time.time(), "text": line, "error": bool(kw.get("error"))})
                    del stream[:-_MAX_SUBAGENT_LINES]

    def to_dict(self) -> dict:
        with self.lock:
            return {
                "id": self.id,
                "cwd": self.cwd,
                "task": self.task,
                "status": self.status,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "events": list(self.events),
                "subagents": [dict(row, stream=list(row["stream"])) for row in self.subagents.values()],
                "verdict": (self.report or {}).get("verdict", ""),
                "note": (self.report or {}).get("note", ""),
                "error": self.error,
            }


_lock = threading.Lock()
_runs: Dict[str, OrchestratorRun] = {}


def _same_cwd(a: str, b: str) -> bool:
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return a == b


def list_runs(cwd: str) -> List[dict]:
    with _lock:
        runs = [run for run in _runs.values() if _same_cwd(run.cwd, cwd)]
    return [run.to_dict() for run in sorted(runs, key=lambda r: r.started_at, reverse=True)]


def stop_run(run_id: str) -> bool:
    with _lock:
        run = _runs.get(run_id)
    if run is None or run.status != "running" or run.coordinator is None:
        return False
    try:
        # Propagates to the flow's running subagents; the flow also checks it
        # between phases.
        run.coordinator.interrupt("Stopped from the Orchestrator tab")
    except Exception:  # noqa: BLE001
        return False
    return True


def _prune_finished() -> None:
    finished = sorted((r for r in _runs.values() if r.status != "running"), key=lambda r: r.finished_at or 0)
    for run in finished[:-_MAX_FINISHED]:
        _runs.pop(run.id, None)


def start_run(
    *,
    cwd: str,
    task: str,
    make_coordinator: CoordinatorFactory,
    run_flow: FlowRunner,
    run_in_context: Callable[[str, Callable[[], None]], None],
    spawn: Callable[[Callable[[], None]], None] = lambda fn: threading.Thread(target=fn, daemon=True).start(),
) -> OrchestratorRun:
    """Register a flow and start it in the background.

    Raises ``RuntimeError`` when the workspace already has a flow running.
    """
    run = OrchestratorRun(id=f"orch_{uuid.uuid4().hex[:8]}", cwd=cwd, task=task.strip())
    with _lock:
        for other in _runs.values():
            if other.status == "running" and _same_cwd(other.cwd, cwd):
                raise RuntimeError("A flow is already running in this workspace")
        _runs[run.id] = run

    def work() -> None:
        try:
            coordinator = make_coordinator(run)
            coordinator.tool_progress_callback = run.record
            run.coordinator = coordinator
            run.report = run_flow(coordinator, run.task)
            run.status = str(run.report.get("verdict") or "failed")
        except Exception as exc:  # noqa: BLE001 — reported on the run, never raised
            run.error = f"{type(exc).__name__}: {exc}"
            run.status = "failed"
        finally:
            run.finished_at = time.time()
            run.coordinator = None
            with _lock:
                _prune_finished()

    spawn(lambda: run_in_context(run.id, work))
    return run


def _reset_for_tests() -> None:
    with _lock:
        _runs.clear()
