"""Behavior contracts for the multi-model orchestrator flow."""

import json

import pytest

from agent import orchestrator as orch
from agent.orchestrator import Assignment, Candidate


def _assign(model="m", provider="p"):
    return {r: Assignment(r, provider, f"{model}-{r}", False) for r in orch.ROLE_IDS}


class TestNormalizeConfig:
    def test_fills_every_role_and_clamps_rounds(self):
        conf = orch.normalize_config({"max_review_rounds": 99, "roles": {"planner": {"model": " x "}}})
        assert set(conf["roles"]) == set(orch.ROLE_IDS)
        assert conf["roles"]["planner"] == {"provider": "", "model": "x"}
        assert conf["max_review_rounds"] == orch.MAX_REVIEW_ROUNDS_CAP
        assert conf["enabled"] is False

    def test_garbage_input_yields_defaults(self):
        conf = orch.normalize_config({"max_review_rounds": "nope", "roles": "bad"})
        assert conf["max_review_rounds"] == orch.DEFAULT_MAX_REVIEW_ROUNDS
        assert all(v == {"provider": "", "model": ""} for v in conf["roles"].values())


class TestAutoAssign:
    def test_every_role_gets_a_usable_model(self):
        pool = [
            Candidate("a", "big-pro", family="alpha", reasoning=True, tool_call=True, cost_output=15),
            Candidate("b", "no-tools", family="beta", reasoning=True, tool_call=False, cost_output=60),
        ]
        picks = orch.auto_assign(pool)
        assert set(picks) == set(orch.ROLE_IDS)
        assert all(p.model == "big-pro" for p in picks.values())

    def test_reviewer_independent_of_executor_family_when_close(self):
        pool = [
            Candidate("a", "alpha-coder", family="alpha", reasoning=True, tool_call=True, cost_output=15),
            Candidate("b", "beta-pro", family="beta", reasoning=True, tool_call=True, cost_output=12),
        ]
        picks = orch.auto_assign(pool)
        assert picks["executor"].model == "alpha-coder"
        assert orch._family_of(pool[1]) != orch._family_of(pool[0])
        assert picks["reviewer"].model == "beta-pro"

    def test_pinned_executor_steers_auto_reviewer(self):
        pool = [
            Candidate("a", "alpha-pro", family="alpha", reasoning=True, tool_call=True, cost_output=15),
            Candidate("b", "beta-pro", family="beta", reasoning=True, tool_call=True, cost_output=14),
        ]
        picks = orch.auto_assign(pool, fixed={"executor": ("b", "beta-pro")}, roles=("reviewer",))
        assert set(picks) == {"reviewer"}
        assert picks["reviewer"].model == "alpha-pro"

    def test_no_candidates_falls_back_to_session_model(self):
        resolved = orch.resolve_assignments(orch.normalize_config({}), candidates=[])
        assert all(a.model == "" and a.auto for a in resolved.values())

    def test_user_pick_is_kept(self):
        conf = orch.normalize_config({"roles": {"reviewer": {"provider": "x", "model": "chosen"}}})
        pool = [Candidate("a", "other", tool_call=True)]
        resolved = orch.resolve_assignments(conf, candidates=pool)
        assert (resolved["reviewer"].provider, resolved["reviewer"].model, resolved["reviewer"].auto) == ("x", "chosen", False)
        assert resolved["planner"].model == "other"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("all good\nVERDICT: APPROVED", "approved"),
        ("1. bug\nVERDICT: CHANGES_REQUESTED", "changes_requested"),
        ("VERDICT: approved then VERDICT: changes requested", "changes_requested"),
        ("no verdict here", "unknown"),
        (None, "unknown"),
    ],
)
def test_parse_verdict(text, expected):
    assert orch.parse_verdict(text) == expected


class _ScriptedRunner:
    """Fake stage runner: reviewers request changes for the first N rounds."""

    def __init__(self, reject_rounds=0, fail_role=None):
        self.reject_rounds = reject_rounds
        self.fail_role = fail_role
        self.calls = []
        self.exec_count = 0

    def __call__(self, parent, assignment, goal):
        self.calls.append((assignment.role, assignment.model, goal))
        if assignment.role == self.fail_role:
            return {"status": "error", "error": "boom"}
        if assignment.role == "executor":
            self.exec_count += 1
            return {"status": "completed", "summary": f"changed files round {self.exec_count}"}
        if assignment.role in ("reviewer", "verifier"):
            if self.exec_count <= self.reject_rounds:
                return {"status": "completed", "summary": f"1. fix bug-{self.exec_count}\nVERDICT: CHANGES_REQUESTED"}
            return {"status": "completed", "summary": "looks right\nVERDICT: APPROVED"}
        return {"status": "completed", "summary": "1. do the thing"}


def _conf(rounds=2):
    return orch.normalize_config({"max_review_rounds": rounds})


class TestRunFlow:
    def test_approved_first_round(self):
        runner = _ScriptedRunner()
        report = orch.run_flow(object(), "add a flag", config=_conf(), assignments=_assign(), runner=runner)
        assert report["verdict"] == "approved" and report["success"] is True
        assert [s["role"] for s in report["stages"]] == ["planner", "executor", "reviewer", "verifier"]
        # Each stage ran on its own assigned model.
        assert {(role, model) for role, model, _ in runner.calls} == {(r, f"m-{r}") for r in orch.ROLE_IDS}
        json.dumps(report)

    def test_findings_loop_back_to_executor(self):
        runner = _ScriptedRunner(reject_rounds=1)
        report = orch.run_flow(object(), "task", config=_conf(), assignments=_assign(), runner=runner)
        assert report["verdict"] == "approved"
        assert report["rounds"] == 2
        second_exec_goal = [g for role, _, g in runner.calls if role == "executor"][1]
        assert "fix bug-1" in second_exec_goal
        assert "1. do the thing" in second_exec_goal  # plan carried forward

    def test_report_stays_bounded_across_rounds(self):
        long = "x" * 20000

        def runner(parent, assignment, goal):
            if assignment.role in ("reviewer", "verifier"):
                return {"status": "completed", "summary": long + "\nVERDICT: CHANGES_REQUESTED"}
            return {"status": "completed", "summary": long}

        report = orch.run_flow(object(), "task", config=_conf(rounds=4), assignments=_assign(), runner=runner)
        assert report["rounds"] == 5
        last = max(s["round"] for s in report["stages"])
        for stage in report["stages"]:
            limit = orch._STAGE_SUMMARY_CHARS if stage["round"] in (0, last) else orch._SUPERSEDED_SUMMARY_CHARS
            assert len(stage["summary"]) <= limit + 64
        assert len(json.dumps(report)) < 60_000

    def test_rounds_are_bounded(self):
        runner = _ScriptedRunner(reject_rounds=99)
        report = orch.run_flow(object(), "task", config=_conf(rounds=1), assignments=_assign(), runner=runner)
        assert report["verdict"] == "changes_requested" and report["success"] is False
        assert runner.exec_count == 2

    def test_failed_planner_stops_the_flow(self):
        runner = _ScriptedRunner(fail_role="planner")
        report = orch.run_flow(object(), "task", config=_conf(), assignments=_assign(), runner=runner)
        assert report["verdict"] == "failed"
        assert [c[0] for c in runner.calls] == ["planner"]

    def test_runner_exception_is_reported_not_raised(self):
        def runner(parent, assignment, goal):
            raise RuntimeError("provider down")

        report = orch.run_flow(object(), "task", config=_conf(), assignments=_assign(), runner=runner)
        assert report["verdict"] == "failed"
        assert "provider down" in report["stages"][0]["error"]


class TestOrchestrateTool:
    def test_gated_on_config(self, monkeypatch):
        from tools import orchestrator_tool

        monkeypatch.setattr(orch, "_load_raw_config", lambda: {"orchestrator": {"enabled": False}})
        assert orchestrator_tool.check_orchestrator_requirements() is False
        monkeypatch.setattr(orch, "_load_raw_config", lambda: {"orchestrator": {"enabled": True}})
        assert orchestrator_tool.check_orchestrator_requirements() is True

    def test_requires_active_parent(self):
        from tools import orchestrator_tool

        result = json.loads(orchestrator_tool.orchestrate_tool("do it"))
        assert "error" in result

    def test_not_inherited_by_subagents(self):
        from tools.delegate_tool import DELEGATE_BLOCKED_TOOLS, _strip_blocked_tools

        assert "orchestrate" in DELEGATE_BLOCKED_TOOLS
        assert "orchestrator" not in _strip_blocked_tools(["orchestrator", "file"])
