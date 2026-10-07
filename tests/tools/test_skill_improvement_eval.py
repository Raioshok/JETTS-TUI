import importlib
import json
import os

import pytest
from tools.skill_improvement_eval import evaluate_candidate, score_skill


@pytest.fixture
def jettstui_home(tmp_path, monkeypatch):
    home = tmp_path / ".jettstui"
    home.mkdir()
    monkeypatch.setenv("JETTSTUI_HOME", os.fspath(home))
    return home


GOOD = """---
name: reliable-tests
description: Use this skill when a code change needs verified tests.
---
# Reliable tests

Only when source code changed:

1. Run `pytest tests/unit`.
2. Verify the command exits with code 0.

## Pitfalls

Do not hide a failure by deleting the assertion. Check the error and fix the cause.
"""


def test_good_skill_has_high_structural_score():
    result = score_skill(GOOD)
    assert result["score"] >= 7
    assert result["failures"] == []


def test_weak_autonomous_create_is_blocked():
    weak = """---
name: vague
description: Helpful notes
---
# Notes

Remember to be thoughtful and produce useful results for the user every time.
"""
    result = evaluate_candidate(action="create", name="vague", candidate=weak)
    assert result["verdict"] == "block"
    assert result["after_score"] < 5


def test_edit_that_drops_multiple_quality_signals_is_blocked():
    reduced = """---
name: reliable-tests
description: Testing advice.
---
# Testing

Run the normal project tests and report the result to the user when finished.
"""
    result = evaluate_candidate(
        action="edit", name="reliable-tests", before=GOOD, candidate=reduced
    )
    assert result["verdict"] == "block"
    assert result["delta"] <= -2


def test_focused_edit_with_equal_score_can_reach_human_review():
    changed = GOOD.replace("pytest tests/unit", "pytest tests/unit -q")
    result = evaluate_candidate(
        action="edit", name="reliable-tests", before=GOOD, candidate=changed
    )
    assert result["verdict"] == "pass"
    assert result["delta"] == 0


def test_background_create_is_scored_and_staged(jettstui_home):
    import jettstui.config as cfg
    import tools.skill_manager_tool as smt
    from tools import write_approval as wa
    from tools.skill_provenance import reset_current_write_origin, set_current_write_origin

    config = cfg.load_config()
    config.setdefault("skills", {})["improvement_gate"] = True
    config["skills"]["write_approval"] = True
    cfg.save_config(config)
    importlib.reload(smt)

    token = set_current_write_origin("background_review")
    try:
        result = json.loads(smt.skill_manage("create", "reliable-tests", content=GOOD))
    finally:
        reset_current_write_origin(token)

    assert result["staged"] is True
    record = wa.get_pending("skills", result["pending_id"])
    evaluation = record["metadata"]["quality_evaluation"]
    assert evaluation["verdict"] == "pass"
    assert evaluation["after_score"] >= 7


def test_background_weak_create_is_rejected_before_staging(jettstui_home):
    import jettstui.config as cfg
    import tools.skill_manager_tool as smt
    from tools import write_approval as wa
    from tools.skill_provenance import reset_current_write_origin, set_current_write_origin

    config = cfg.load_config()
    config.setdefault("skills", {})["improvement_gate"] = True
    config["skills"]["write_approval"] = True
    cfg.save_config(config)
    importlib.reload(smt)
    weak = """---
name: vague
description: Helpful notes
---
# Notes

Remember to be thoughtful and produce useful results for the user every time.
"""

    token = set_current_write_origin("background_review")
    try:
        result = json.loads(smt.skill_manage("create", "vague", content=weak))
    finally:
        reset_current_write_origin(token)

    assert result["success"] is False
    assert "locked evaluator" in result["error"]
    assert wa.pending_count("skills") == 0
