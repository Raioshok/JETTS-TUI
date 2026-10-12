"""Headless spec runs for the desktop Specs page.

The Specs page drives the spec workflow (``jettstui/specs.py``) without
opening chats: each action becomes a *spec run* — a hidden agent that works in
the spec's workspace with the phase's work mode, records its activity here,
and leaves no session behind (``session_db=None``), so spec work never shows
up in the session list. The page polls ``spec.runs`` to show progress and the
agent's final reply in place.

One run per spec at a time: a second action on a spec that is still being
worked on is refused, which is also what stops a double click from starting
the same work twice.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional

# Bounded memory: activity lines per run, finished runs kept per process.
_MAX_ACTIVITY = 40
_MAX_FINISHED = 30
_SUMMARY_CHARS = 6000

# Machine-generated texts a turn can end with that are not the agent's reply:
# run_agent's cancellation sentinel and its turn-failure notice.
_CANCELLED_PREFIX = "Operation interrupted:"
_FAILURE_PREFIXES = ("⚠️ No reply:", "No reply:")

AgentFactory = Callable[["SpecRun"], Any]
"""run -> an AIAgent-like object (run_conversation, interrupt) for that run."""


@dataclass
class SpecRun:
    id: str
    cwd: str
    spec: str
    label: str
    mode: str
    # The /spec arguments that redo this run's step (Retry on the page).
    retry_args: str = ""
    status: str = "running"  # running | completed | failed | interrupted
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    activity: Deque[dict] = field(default_factory=lambda: deque(maxlen=_MAX_ACTIVITY))
    summary: str = ""
    error: str = ""
    agent: Any = None
    # Set by Stop. Honoured even while the agent is still being built, when
    # there is nothing to interrupt yet.
    stop_requested: bool = False

    def note(self, text: str, kind: str = "progress") -> None:
        text = " ".join(str(text or "").split())
        if text:
            self.activity.append({"at": time.time(), "kind": kind, "text": text[:240]})

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "cwd": self.cwd,
            "spec": self.spec,
            "label": self.label,
            "mode": self.mode,
            "retry_args": self.retry_args,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "activity": list(self.activity),
            "summary": self.summary,
            "error": self.error,
        }


_lock = threading.Lock()
_runs: Dict[str, SpecRun] = {}


def _same_cwd(a: str, b: str) -> bool:
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return a == b


def active_run(cwd: str, spec: str) -> Optional[SpecRun]:
    with _lock:
        for run in _runs.values():
            if run.status == "running" and run.spec == spec and _same_cwd(run.cwd, cwd):
                return run
    return None


def list_runs(cwd: str) -> List[dict]:
    """Runs for a workspace, newest first."""
    with _lock:
        runs = [run for run in _runs.values() if _same_cwd(run.cwd, cwd)]
    return [run.to_dict() for run in sorted(runs, key=lambda r: r.started_at, reverse=True)]


def stop_run(run_id: str) -> bool:
    with _lock:
        run = _runs.get(run_id)
        if run is None or run.status != "running":
            return False
        run.stop_requested = True
        agent = run.agent
    if agent is not None:
        try:
            agent.interrupt("Stopped from the Specs page")
        except Exception:  # noqa: BLE001 — a dead agent is already stopping
            pass
    run.note("Stopping…", "status")
    return True


def _prune_finished() -> None:
    finished = sorted(
        (r for r in _runs.values() if r.status != "running"), key=lambda r: r.finished_at or 0
    )
    for run in finished[:-_MAX_FINISHED]:
        _runs.pop(run.id, None)


def callbacks_for(run: SpecRun) -> dict:
    """Agent callbacks that turn tool activity into the run's activity log."""

    def tool_start(_tool_call_id: str, name: str, args: Any) -> None:
        target = ""
        if isinstance(args, dict):
            target = str(args.get("path") or args.get("command") or args.get("query") or "")
        run.note(f"{name}  {target}".strip(), "tool")

    def status(kind: Any, text: Any = None) -> None:
        if text:
            run.note(str(text), "status")

    return {"tool_start_callback": tool_start, "status_callback": status}


def start_run(
    *,
    cwd: str,
    spec: str,
    label: str,
    seed: str,
    mode: str,
    make_agent: AgentFactory,
    retry_args: str = "",
    run_in_context: Callable[[str, Callable[[], None]], None],
    spawn: Callable[[Callable[[], None]], None] = lambda fn: threading.Thread(target=fn, daemon=True).start(),
) -> SpecRun:
    """Register a run and start its agent in the background.

    ``run_in_context(task_id, fn)`` binds the workspace (cwd, task env) around
    ``fn``; ``spawn`` is injectable so tests can run synchronously.
    Raises ``RuntimeError`` when the spec already has a run in progress.
    """
    task_id = f"spec_{uuid.uuid4().hex[:8]}"
    run = SpecRun(id=task_id, cwd=cwd, spec=spec, label=label, mode=mode, retry_args=retry_args)
    with _lock:
        for other in _runs.values():
            if other.status == "running" and other.spec == spec and _same_cwd(other.cwd, cwd):
                raise RuntimeError(f"'{spec}' is already being worked on")
        _runs[task_id] = run

    def work() -> None:
        try:
            agent = make_agent(run)
            with _lock:
                run.agent = agent
                stopped_early = run.stop_requested
            if stopped_early:
                # Stopped while the agent was starting: don't begin the turn.
                run.status = "interrupted"
                return
            run.note(label, "status")
            result = agent.run_conversation(user_message=seed, task_id=task_id)
            text = result.get("final_response", "") if isinstance(result, dict) else str(result or "")
            text = str(text or "").strip()
            interrupted = run.stop_requested or bool(getattr(agent, "_interrupt_requested", False)) or (
                isinstance(result, dict) and result.get("interrupted")
            )
            if interrupted:
                # The cancellation sentinel is metadata, not a reply; keep any
                # real text the agent had already produced.
                run.status = "interrupted"
                run.summary = "" if text.startswith(_CANCELLED_PREFIX) else text[:_SUMMARY_CHARS]
            elif isinstance(result, dict) and result.get("failed"):
                # The turn gave up (e.g. "API call failed after 3 retries: …");
                # its final_response is an error notice, not a reply.
                run.status = "failed"
                run.error = str(result.get("error") or text)[:_SUMMARY_CHARS]
            elif text.startswith(_FAILURE_PREFIXES):
                run.status = "failed"
                run.error = text.split(":", 1)[1].strip()[:_SUMMARY_CHARS]
            else:
                run.status = "completed"
                run.summary = text[:_SUMMARY_CHARS]
        except Exception as exc:  # noqa: BLE001 — reported on the run, never raised
            run.error = f"{type(exc).__name__}: {exc}"
            run.status = "failed"
        finally:
            run.finished_at = time.time()
            run.agent = None
            with _lock:
                _prune_finished()

    spawn(lambda: run_in_context(task_id, work))
    return run


def _reset_for_tests() -> None:
    with _lock:
        _runs.clear()
