"""Behavior contracts for the multi-model orchestrator flow."""

import json
import threading

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
        assert conf["auto_balance"] == orch.DEFAULT_BALANCE

    def test_garbage_input_yields_defaults(self):
        conf = orch.normalize_config({"max_review_rounds": "nope", "roles": "bad", "auto_balance": 3})
        assert conf["max_review_rounds"] == orch.DEFAULT_MAX_REVIEW_ROUNDS
        assert all(v == {"provider": "", "model": ""} for v in conf["roles"].values())
        assert conf["auto_balance"] == orch.DEFAULT_BALANCE

    def test_balance_is_case_insensitive(self):
        assert orch.normalize_config({"auto_balance": "Economy"})["auto_balance"] == "economy"


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


class TestCostQualityBalance:
    POOL = [
        Candidate("p", "cheap-mini", family="a", reasoning=True, tool_call=True, cost_input=0.15, cost_output=0.6),
        Candidate("p", "mid-model", family="b", reasoning=True, tool_call=True, cost_input=3, cost_output=15),
        Candidate("p", "premium-model", family="c", reasoning=True, tool_call=True, cost_input=15, cost_output=75),
    ]

    def _avg_price(self, balance):
        picks = orch.auto_assign(self.POOL, balance=balance)
        by_name = {c.model: c for c in self.POOL}
        return sum(orch._blended_price(by_name[p.model]) for p in picks.values()) / len(picks)

    def test_balance_modes_order_total_spend(self):
        assert self._avg_price("economy") < self._avg_price("balanced") < self._avg_price("quality")

    def test_every_role_pays_for_cost(self):
        # A pricier model scores below its quality edge for every role: cost
        # is weighed in all of them, not only the executor.
        cheap, rich = self.POOL[1], self.POOL[2]
        for role in orch.ROLE_IDS:
            quality_gain = orch.quality_estimate(rich, role) - orch.quality_estimate(cheap, role)
            value_gain = orch.score_candidate(rich, role) - orch.score_candidate(cheap, role)
            assert value_gain < quality_gain

    def test_quality_has_diminishing_returns(self):
        cheap, mid, rich = self.POOL
        role = "executor"
        low_step = orch.quality_estimate(mid, role) - orch.quality_estimate(cheap, role)
        high_step = orch.quality_estimate(rich, role) - orch.quality_estimate(mid, role)
        assert high_step < low_step

    def test_cost_tier_reported_for_priced_models(self):
        picks = orch.auto_assign(self.POOL, balance="quality")
        assert all(p.cost_tier.startswith("$") for p in picks.values())

    def test_resolve_uses_configured_balance(self):
        cheap = orch.resolve_assignments(orch.normalize_config({"auto_balance": "economy"}), candidates=self.POOL)
        rich = orch.resolve_assignments(orch.normalize_config({"auto_balance": "quality"}), candidates=self.POOL)
        assert cheap["executor"].model != rich["executor"].model


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


def _phase(goal):
    return "verify" if "· verify]" in goal else "work"


class _ScriptedRunner:
    """Fake stage runner: verify-phase judges reject the first N rounds."""

    def __init__(self, reject_rounds=0, fail_role=None):
        self.reject_rounds = reject_rounds
        self.fail_role = fail_role
        self.calls = []
        self.exec_count = 0
        self._lock = threading.Lock()

    def __call__(self, parent, assignment, goal, on_spawn=None):
        phase = _phase(goal)
        with self._lock:
            self.calls.append((assignment.role, phase, assignment.model, goal))
            if on_spawn:
                on_spawn(f"sa-{assignment.role}-{len(self.calls)}")
            if assignment.role == self.fail_role:
                return {"status": "error", "error": "boom"}
            if phase == "work":
                if assignment.role == "executor":
                    self.exec_count += 1
                    return {"status": "completed", "summary": f"changed files round {self.exec_count}"}
                if assignment.role == "planner":
                    return {"status": "completed", "summary": "1. do the thing"}
                return {"status": "completed", "summary": f"{assignment.role} notes"}
            if self.exec_count <= self.reject_rounds:
                return {"status": "completed", "summary": f"1. fix bug-{self.exec_count}\nVERDICT: CHANGES_REQUESTED"}
            return {"status": "completed", "summary": "looks right\nVERDICT: APPROVED"}


class _Recorder:
    """Parent agent stand-in that records relayed progress events."""

    def __init__(self):
        self.events = []
        self._interrupt_requested = False

    def tool_progress_callback(self, event_type, name=None, preview=None, args=None, **kw):
        self.events.append((event_type, kw.get("flow")))


def _run(runner, board, rounds=2, parent=None):
    return orch.run_flow(
        parent or object(),
        "add a flag",
        config=orch.normalize_config({"max_review_rounds": rounds}),
        assignments=_assign(),
        runner=runner,
        board=board,
    )


class TestRunFlow:
    def test_every_role_works_then_judges_on_its_own_model(self, tmp_path):
        runner = _ScriptedRunner()
        report = _run(runner, tmp_path)
        assert report["verdict"] == "approved" and report["success"] is True
        work = {(r, m) for r, ph, m, _ in runner.calls if ph == "work"}
        verify = {(r, m) for r, ph, m, _ in runner.calls if ph == "verify"}
        assert work == {(r, f"m-{r}") for r in orch.WORK_ROLES}
        assert verify == {(r, f"m-{r}") for r in orch.VERIFY_ROLES}
        assert all(("verdict" in s) == (s["phase"] == "verify") for s in report["stages"])
        json.dumps(report)

    def test_work_phase_runs_all_roles_at_the_same_time(self, tmp_path):
        barrier = threading.Barrier(len(orch.WORK_ROLES), timeout=10)
        inner = _ScriptedRunner()

        def runner(parent, assignment, goal, on_spawn=None):
            if _phase(goal) == "work":
                barrier.wait()  # BrokenBarrierError unless every role is in flight at once
            return inner(parent, assignment, goal, on_spawn)

        assert _run(runner, tmp_path)["verdict"] == "approved"

    def test_verify_phase_runs_all_judges_at_the_same_time(self, tmp_path):
        barrier = threading.Barrier(len(orch.VERIFY_ROLES), timeout=10)
        inner = _ScriptedRunner()

        def runner(parent, assignment, goal, on_spawn=None):
            if _phase(goal) == "verify":
                barrier.wait()
            return inner(parent, assignment, goal, on_spawn)

        assert _run(runner, tmp_path)["verdict"] == "approved"

    def test_every_agent_is_pointed_at_every_board_file(self, tmp_path):
        runner = _ScriptedRunner()
        _run(runner, tmp_path)
        for _, _, _, goal in runner.calls:
            assert all(str(tmp_path / f"{r}.md") in goal for r in orch.ROLE_IDS)

    def test_create_board_seeds_one_file_per_role(self):
        board = orch.create_board("run1", "the task")
        assert "the task" in (board / "README.md").read_text(encoding="utf-8")
        assert {p.stem for p in board.glob("*.md")} == set(orch.ROLE_IDS) | {"README"}

    def test_old_boards_are_pruned(self):
        for i in range(orch._KEEP_BOARDS + 3):
            board = orch.create_board(f"run{i}", "t")
        assert len([p for p in board.parent.iterdir() if p.is_dir()]) == orch._KEEP_BOARDS

    def test_findings_loop_back_into_the_next_round(self, tmp_path):
        runner = _ScriptedRunner(reject_rounds=1)
        report = _run(runner, tmp_path)
        assert report["verdict"] == "approved"
        assert report["rounds"] == 2
        second_round_exec = [g for r, ph, _, g in runner.calls if r == "executor" and ph == "work"][1]
        assert "fix bug-1" in second_round_exec
        assert "1. do the thing" in second_round_exec  # plan carried forward

    def test_judges_see_executor_report_and_their_gathered_pieces(self, tmp_path):
        runner = _ScriptedRunner()
        _run(runner, tmp_path)
        reviewer_verify = next(g for r, ph, _, g in runner.calls if r == "reviewer" and ph == "verify")
        assert "changed files round 1" in reviewer_verify
        assert "reviewer notes" in reviewer_verify

    def test_any_rejecting_judge_blocks_approval(self, tmp_path):
        inner = _ScriptedRunner()

        def runner(parent, assignment, goal, on_spawn=None):
            if assignment.role == "planner" and _phase(goal) == "verify":
                return {"status": "completed", "summary": "step 3 missing\nVERDICT: CHANGES_REQUESTED"}
            return inner(parent, assignment, goal, on_spawn)

        assert _run(runner, tmp_path, rounds=0)["verdict"] == "changes_requested"

    def test_report_stays_bounded_across_rounds(self, tmp_path):
        long = "x" * 20000

        def runner(parent, assignment, goal, on_spawn=None):
            if _phase(goal) == "verify":
                return {"status": "completed", "summary": long + "\nVERDICT: CHANGES_REQUESTED"}
            return {"status": "completed", "summary": long}

        report = _run(runner, tmp_path, rounds=4)
        assert report["rounds"] == 5
        assert len(json.dumps(report)) < 60_000

    def test_rounds_are_bounded(self, tmp_path):
        runner = _ScriptedRunner(reject_rounds=99)
        report = _run(runner, tmp_path, rounds=1)
        assert report["verdict"] == "changes_requested" and report["success"] is False
        assert runner.exec_count == 2

    def test_failed_planner_does_not_stop_the_executor(self, tmp_path):
        runner = _ScriptedRunner(fail_role="planner")
        report = _run(runner, tmp_path, rounds=0)
        assert any(s["role"] == "executor" and s["status"] == "completed" for s in report["stages"])
        assert any(ph == "verify" for _, ph, _, _ in runner.calls)

    def test_failed_executor_fails_the_flow(self, tmp_path):
        runner = _ScriptedRunner(fail_role="executor")
        report = _run(runner, tmp_path)
        assert report["verdict"] == "failed"
        assert not any(ph == "verify" for _, ph, _, _ in runner.calls)

    def test_runner_exception_is_reported_not_raised(self, tmp_path):
        def runner(parent, assignment, goal, on_spawn=None):
            raise RuntimeError("provider down")

        report = _run(runner, tmp_path)
        assert report["verdict"] == "failed"
        assert any("provider down" in s.get("error", "") for s in report["stages"])

    def test_interrupt_stops_before_the_next_phase(self, tmp_path):
        parent = _Recorder()
        inner = _ScriptedRunner()

        def runner(p, assignment, goal, on_spawn=None):
            parent._interrupt_requested = True
            return inner(p, assignment, goal, on_spawn)

        report = _run(runner, tmp_path, parent=parent)
        assert report["verdict"] == "interrupted"
        assert not any(ph == "verify" for _, ph, _, _ in inner.calls)


class TestFlowEvents:
    def test_stage_events_bracket_every_stage_and_carry_subagent_ids(self, tmp_path):
        parent = _Recorder()
        _run(_ScriptedRunner(), tmp_path, parent=parent)
        stages = [p for t, p in parent.events if t == "orchestrator.stage"]
        done = [p for p in stages if p["status"] != "running"]
        assert len(done) == len(orch.WORK_ROLES) + len(orch.VERIFY_ROLES)
        assert all(p["run_id"] == tmp_path.name for p in stages)
        spawned = {(p["role"], p["phase"]) for p in stages if p.get("subagent_id")}
        assert spawned == {(p["role"], p["phase"]) for p in done}

    def test_stage_gist_drops_the_verdict_line(self, tmp_path):
        parent = _Recorder()
        _run(_ScriptedRunner(), tmp_path, parent=parent)
        judged = [p for t, p in parent.events if t == "orchestrator.stage" and p.get("verdict")]
        assert judged and all("VERDICT" not in p.get("summary", "") for p in judged)
        assert all(p["verdict"] == "approved" for p in judged)

    def test_finished_stage_carries_its_full_report(self, tmp_path):
        parent = _Recorder()
        _run(_ScriptedRunner(), tmp_path, parent=parent)
        done = [p for t, p in parent.events if t == "orchestrator.stage" and p["status"] == "completed"]
        assert any("VERDICT: APPROVED" in p["report"] for p in done)
        assert any(p["report"] == "1. do the thing" for p in done)

    def test_read_board_only_serves_issued_runs_and_roles(self):
        board = orch.create_board("abc123", "task")
        (board / "executor.md").write_text("changed x", encoding="utf-8")
        assert orch.read_board("abc123", "executor") == "changed x"
        assert orch.read_board("abc123", "../../config") is None
        assert orch.read_board("../runs", "executor") is None
        assert orch.read_board("missing", "executor") is None

    def test_run_events_end_with_the_verdict(self, tmp_path):
        parent = _Recorder()
        report = _run(_ScriptedRunner(), tmp_path, parent=parent)
        runs = [p for t, p in parent.events if t == "orchestrator.run"]
        assert runs[0]["status"] == "running" and runs[0]["phase"] == "work"
        assert runs[-1]["status"] == report["verdict"]
        assert set(runs[-1]["assignments"]) == set(orch.ROLE_IDS)
        json.dumps(runs)

    def test_relay_failure_never_breaks_the_flow(self, tmp_path):
        class Broken:
            def tool_progress_callback(self, *a, **kw):
                raise RuntimeError("ui gone")

        assert _run(_ScriptedRunner(), tmp_path, parent=Broken())["verdict"] == "approved"


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
