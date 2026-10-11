"""spec.list / spec.get / orchestrator.board RPCs against real files."""

from pathlib import Path

from jettstui.specs import run_spec_command
from tui_gateway import server


def _call(method: str, **params):
    return server.handle_request({"id": "t", "method": method, "params": params})


def test_spec_list_and_get_read_the_workspace(tmp_path: Path):
    run_spec_command("new Offline Search", tmp_path)
    spec = tmp_path / ".kiro" / "specs" / "offline-search"
    (spec / "requirements.md").write_text("# Requirements Document\n", encoding="utf-8")
    (spec / "design.md").write_text("# Design Document\n", encoding="utf-8")
    (spec / "tasks.md").write_text("# Implementation Plan\n\n- [ ] 1. Build it\n", encoding="utf-8")

    listed = _call("spec.list", cwd=str(tmp_path))["result"]["specs"]
    assert [s["name"] for s in listed] == ["offline-search"]
    assert listed[0]["phase"] == "tasks"

    detail = _call("spec.get", cwd=str(tmp_path), name="offline-search")["result"]
    assert detail["content"]["requirements"].startswith("# Requirements Document")
    assert detail["tasks"][0]["title"] == "Build it"
    assert detail["next_task"] == "1"


def test_spec_rpcs_tolerate_missing_workspaces(tmp_path: Path):
    assert _call("spec.list", cwd="")["result"]["specs"] == []
    assert _call("spec.list", cwd=str(tmp_path / "nope"))["result"]["specs"] == []
    assert "error" in _call("spec.get", cwd=str(tmp_path), name="missing")


def test_orchestrator_board_rpc(tmp_path: Path):
    from agent.orchestrator import create_board

    board = create_board("run42", "task")
    (board / "reviewer.md").write_text("1. null check missing", encoding="utf-8")

    assert _call("orchestrator.board", run_id="run42", role="reviewer")["result"]["content"] == "1. null check missing"
    assert "error" in _call("orchestrator.board", run_id="run42", role="../../x")
