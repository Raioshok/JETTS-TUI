"""Headless orchestrator flows: the Orchestrator tab works without chats."""

import time
from pathlib import Path

import pytest

from tui_gateway import orchestrator_runs, server


@pytest.fixture(autouse=True)
def _clean_runs():
    orchestrator_runs._reset_for_tests()
    yield
    orchestrator_runs._reset_for_tests()


class FakeCoordinator:
    instances: list = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.tool_progress_callback = None
        self._interrupt_requested = False
        FakeCoordinator.instances.append(self)

    def interrupt(self, message=None):
        self._interrupt_requested = True


def fake_flow(coordinator, task):
    """Emits what agent.orchestrator.run_flow + delegate relays would."""
    cb = coordinator.tool_progress_callback
    cb("orchestrator.run", None, None, None, flow={"run_id": "r1", "status": "running", "task": task, "round": 1})
    cb("orchestrator.stage", None, None, None,
       flow={"run_id": "r1", "role": "executor", "phase": "work", "round": 1, "status": "running", "subagent_id": "sa-1"})
    cb("subagent.tool", "write_file", "src/app.py", None, subagent_id="sa-1", model="m", child_session_id="child-1")
    cb("subagent.text", None, "token", None, subagent_id="sa-1")  # per-token noise: ignored
    cb("subagent.complete", None, "done", None, subagent_id="sa-1", status="completed")
    cb("orchestrator.run", None, None, None, flow={"run_id": "r1", "status": "approved", "round": 1})
    return {"verdict": "approved", "note": "Every verifier approved."}


def _call(method: str, **params):
    return server.handle_request({"id": "t", "method": method, "params": params})


def _wait_finished(cwd: Path, timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        runs = _call("orchestrator.runs", cwd=str(cwd))["result"]["runs"]
        if runs and runs[0]["status"] != "running":
            return runs[0]
        time.sleep(0.02)
    raise AssertionError("flow never finished")


def test_rpc_runs_a_flow_headlessly_and_records_it(monkeypatch, tmp_path: Path):
    import run_agent
    from agent import orchestrator

    FakeCoordinator.instances = []
    monkeypatch.setattr(run_agent, "AIAgent", lambda **kw: FakeCoordinator(**kw))
    monkeypatch.setattr(orchestrator, "run_flow", fake_flow)

    started = _call("orchestrator.run", cwd=str(tmp_path), task="add a flag")["result"]["run"]
    assert started["status"] == "running"

    run = _wait_finished(tmp_path)
    assert run["status"] == "approved" and run["note"] == "Every verifier approved."
    assert [e["type"] for e in run["events"]] == [
        "orchestrator.run", "orchestrator.stage", "orchestrator.run"
    ]
    assert all(isinstance(e["at"], float) for e in run["events"])

    (sub,) = run["subagents"]
    assert sub["id"] == "sa-1" and sub["status"] == "completed"
    # Hidden subagents are never stored: no session to offer opening.
    assert "session_id" not in sub
    assert [line["text"] for line in sub["stream"]] == ["write_file src/app.py"]

    # Hidden: the coordinator keeps no session and no memory.
    coordinator = FakeCoordinator.instances[0]
    assert coordinator.kwargs["session_db"] is None and coordinator.kwargs["skip_memory"] is True
    # ...and never writes one lazily; its subagents inherit this.
    assert coordinator._persist_disabled is True


def test_rpc_validates_input(tmp_path: Path):
    assert _call("orchestrator.run", cwd=str(tmp_path), task=" ")["error"]["code"] == 4001
    assert _call("orchestrator.run", cwd="", task="x")["error"]["code"] == 4001


def test_one_flow_per_workspace(tmp_path: Path):
    held = []
    kwargs = dict(
        cwd=str(tmp_path), task="t", make_coordinator=lambda r: FakeCoordinator(),
        run_flow=fake_flow, run_in_context=lambda _id, fn: fn(), spawn=held.append,
    )
    orchestrator_runs.start_run(**kwargs)
    with pytest.raises(RuntimeError):
        orchestrator_runs.start_run(**kwargs)
    other = tmp_path / "other"
    other.mkdir()
    orchestrator_runs.start_run(**{**kwargs, "cwd": str(other)})
    assert len(held) == 2

    refused = _call("orchestrator.run", cwd=str(tmp_path), task="again")
    assert refused["error"]["code"] == 4009


def test_failure_is_reported_on_the_run(tmp_path: Path):
    def boom(coordinator, task):
        raise RuntimeError("provider down")

    run = orchestrator_runs.start_run(
        cwd=str(tmp_path), task="t", make_coordinator=lambda r: FakeCoordinator(),
        run_flow=boom, run_in_context=lambda _id, fn: fn(), spawn=lambda fn: fn(),
    )
    assert run.status == "failed" and "provider down" in run.error


def test_stop_interrupts_the_coordinator(tmp_path: Path):
    coordinator = FakeCoordinator()
    run = orchestrator_runs.start_run(
        cwd=str(tmp_path), task="t", make_coordinator=lambda r: coordinator,
        run_flow=fake_flow, run_in_context=lambda _id, fn: None, spawn=lambda fn: None,
    )
    run.coordinator = coordinator
    assert _call("orchestrator.stop", run_id=run.id)["result"]["stopped"] is True
    assert coordinator._interrupt_requested is True
    assert _call("orchestrator.stop", run_id="nope")["result"]["stopped"] is False


def test_subagent_log_is_bounded_and_deduplicated(tmp_path: Path):
    run = orchestrator_runs.OrchestratorRun(id="x", cwd=str(tmp_path), task="t")
    for i in range(100):
        run.record("subagent.tool", "read_file", f"f{i}.py", None, subagent_id="sa")
        run.record("subagent.tool", "read_file", f"f{i}.py", None, subagent_id="sa")
    stream = run.to_dict()["subagents"][0]["stream"]
    assert len(stream) == orchestrator_runs._MAX_SUBAGENT_LINES
    assert len({line["text"] for line in stream}) == len(stream)


def test_stop_before_the_coordinator_exists_is_honoured(tmp_path: Path):
    flows = []
    held = []
    run = orchestrator_runs.start_run(
        cwd=str(tmp_path), task="t", make_coordinator=lambda r: FakeCoordinator(),
        run_flow=lambda c, t: flows.append(t) or {"verdict": "approved"},
        run_in_context=lambda _id, fn: fn(), spawn=held.append,
    )
    assert orchestrator_runs.stop_run(run.id) is True
    held[0]()
    assert run.status == "interrupted" and flows == []
