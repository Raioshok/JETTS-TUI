"""Headless spec runs: the Specs page works without opening chats."""

import time
from pathlib import Path

import pytest

from tui_gateway import server, spec_runs


@pytest.fixture(autouse=True)
def _clean_runs():
    spec_runs._reset_for_tests()
    yield
    spec_runs._reset_for_tests()


class FakeAgent:
    """Stands in for AIAgent: writes the phase document like the model would."""

    instances: list = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self._work_mode = "default"
        self._interrupt_requested = False
        FakeAgent.instances.append(self)

    def run_conversation(self, user_message, task_id=None):
        self.seed = user_message
        self.kwargs["tool_start_callback"]("c1", "write_file", {"path": "requirements.md"})
        cwd = Path(self.kwargs["_cwd"])
        target = cwd / ".kiro" / "specs" / "offline-search" / "requirements.md"
        target.write_text("# Requirements Document\n", encoding="utf-8")
        return {"final_response": "Do the requirements look good?"}

    def interrupt(self, message=None):
        self._interrupt_requested = True


def _call(method: str, **params):
    return server.handle_request({"id": "t", "method": method, "params": params})


def _wait_finished(cwd: Path, timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        runs = _call("spec.runs", cwd=str(cwd))["result"]["runs"]
        if runs and runs[0]["status"] != "running":
            return runs[0]
        time.sleep(0.02)
    raise AssertionError("spec run never finished")


@pytest.fixture
def fake_agent(monkeypatch, tmp_path):
    import run_agent

    FakeAgent.instances = []

    def build(**kwargs):
        kwargs["_cwd"] = str(tmp_path)
        return FakeAgent(**kwargs)

    monkeypatch.setattr(run_agent, "AIAgent", build)
    return FakeAgent


def test_spec_run_works_headlessly_and_reports_back(tmp_path: Path, fake_agent):
    started = _call("spec.run", cwd=str(tmp_path), args="new Offline Search")["result"]
    assert started["spec"] == "offline-search"
    assert started["run"]["status"] == "running"

    run = _wait_finished(tmp_path)
    assert run["status"] == "completed"
    assert run["summary"] == "Do the requirements look good?"
    assert any("write_file" in line["text"] for line in run["activity"])
    assert (tmp_path / ".kiro/specs/offline-search/requirements.md").exists()

    agent = fake_agent.instances[0]
    # Hidden: no session record or memory, no clarify, and the phase's mode.
    assert agent.kwargs["session_db"] is None
    assert agent.kwargs["skip_memory"] is True
    assert "clarify" in agent.kwargs["disabled_toolsets"]
    assert agent._work_mode == "plan"
    assert "REQUIREMENTS phase" in agent.seed


def test_actions_without_agent_work_just_answer(tmp_path: Path, fake_agent):
    result = _call("spec.run", cwd=str(tmp_path), args="list")["result"]
    assert result["run"] is None and "No specs yet" in result["output"]
    assert fake_agent.instances == []


def test_one_run_per_spec_at_a_time(tmp_path: Path):
    calls = []

    def make_agent(run):
        calls.append(run.id)
        return FakeAgent(_cwd=str(tmp_path), tool_start_callback=lambda *a: None)

    held = []
    spec_runs.start_run(
        cwd=str(tmp_path), spec="s", label="x", seed="go", mode="plan",
        make_agent=make_agent, run_in_context=lambda _id, fn: fn(), spawn=held.append,
    )
    with pytest.raises(RuntimeError):
        spec_runs.start_run(
            cwd=str(tmp_path), spec="s", label="x", seed="go", mode="plan",
            make_agent=make_agent, run_in_context=lambda _id, fn: fn(), spawn=held.append,
        )
    # A different spec in the same workspace is fine.
    spec_runs.start_run(
        cwd=str(tmp_path), spec="other", label="x", seed="go", mode="plan",
        make_agent=make_agent, run_in_context=lambda _id, fn: fn(), spawn=held.append,
    )
    assert len(held) == 2


def test_rpc_refuses_a_second_action_on_a_busy_spec(tmp_path: Path):
    spec_runs.start_run(
        cwd=str(tmp_path), spec="offline-search", label="x", seed="go", mode="plan",
        make_agent=lambda run: None, run_in_context=lambda _id, fn: None, spawn=lambda fn: None,
    )
    refused = _call("spec.run", cwd=str(tmp_path), args="approve offline-search requirements")
    assert refused["error"]["code"] == 4009


def test_failures_and_stops_are_reported_on_the_run(tmp_path: Path):
    class Boom(FakeAgent):
        def run_conversation(self, user_message, task_id=None):
            raise RuntimeError("provider down")

    run = spec_runs.start_run(
        cwd=str(tmp_path), spec="s", label="x", seed="go", mode="plan",
        make_agent=lambda r: Boom(), run_in_context=lambda _id, fn: fn(), spawn=lambda fn: fn(),
    )
    assert run.status == "failed" and "provider down" in run.error

    class Interrupted(FakeAgent):
        def run_conversation(self, user_message, task_id=None):
            self._interrupt_requested = True
            return {"final_response": "", "interrupted": True}

    run = spec_runs.start_run(
        cwd=str(tmp_path), spec="t", label="x", seed="go", mode="plan",
        make_agent=lambda r: Interrupted(), run_in_context=lambda _id, fn: fn(), spawn=lambda fn: fn(),
    )
    assert run.status == "interrupted"


def test_stop_interrupts_the_running_agent(tmp_path: Path):
    agent = FakeAgent()
    held = []
    run = spec_runs.start_run(
        cwd=str(tmp_path), spec="s", label="x", seed="go", mode="plan",
        make_agent=lambda r: agent, run_in_context=lambda _id, fn: fn(), spawn=held.append,
    )
    run.agent = agent
    assert _call("spec.stop", run_id=run.id)["result"]["stopped"] is True
    assert agent._interrupt_requested is True
    assert _call("spec.stop", run_id="nope")["result"]["stopped"] is False


def test_runs_are_scoped_to_their_workspace(tmp_path: Path):
    other = tmp_path / "other"
    other.mkdir()
    spec_runs.start_run(
        cwd=str(tmp_path), spec="s", label="x", seed="go", mode="plan",
        make_agent=lambda r: None, run_in_context=lambda _id, fn: None, spawn=lambda fn: None,
    )
    assert len(_call("spec.runs", cwd=str(tmp_path))["result"]["runs"]) == 1
    assert _call("spec.runs", cwd=str(other))["result"]["runs"] == []
