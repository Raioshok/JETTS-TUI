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


STANDARD_SHAPE = """---
name: release-notes
description: Drafts release notes from merged pull requests.
---
# Release Notes Skill

## When to Use

Only when a release tag is being prepared.

## Procedure

1. Run `git log --merges v1.0..HEAD`.
2. Group entries by area.

## Pitfalls

Do not list reverted changes.

## Verification

Check every listed PR is merged.
"""


def test_when_to_use_section_counts_as_trigger():
    """A skill written to the repo standard (short description, trigger in a
    When to Use section) must not lose the trigger signal."""
    assert "explicit trigger" in score_skill(STANDARD_SHAPE)["signals"]


def test_crlf_and_bom_frontmatter_is_parsed():
    windows = "﻿" + GOOD.replace("\n", "\r\n")
    result = score_skill(windows)
    assert result["failures"] == []
    assert result["score"] == score_skill(GOOD)["score"]


def test_near_duplicate_create_is_blocked_with_pointer():
    existing = [
        {"name": "reliable-tests", "description": "Use this skill when a code change needs verified tests."},
        {"name": "release-notes", "description": "Drafts release notes from merged pull requests."},
    ]
    paraphrase = GOOD.replace("name: reliable-tests", "name: verified-tests-for-code-changes")
    result = evaluate_candidate(
        action="create", name="verified-tests-for-code-changes", candidate=paraphrase, existing=existing
    )
    assert result["verdict"] == "block"
    assert result["duplicate_of"] == "reliable-tests"
    assert any("patch that skill" in reason for reason in result["reasons"])


def test_distinct_create_passes_duplicate_check():
    existing = [{"name": "reliable-tests", "description": "Use this skill when a code change needs verified tests."}]
    result = evaluate_candidate(
        action="create", name="release-notes", candidate=STANDARD_SHAPE, existing=existing
    )
    assert result["duplicate_of"] is None
    assert result["verdict"] == "pass"


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


def test_background_near_duplicate_create_is_rejected_end_to_end(jettstui_home):
    import jettstui.config as cfg
    import tools.skill_manager_tool as smt
    from tools import write_approval as wa
    from tools.skill_provenance import reset_current_write_origin, set_current_write_origin

    config = cfg.load_config()
    config.setdefault("skills", {})["improvement_gate"] = True
    config["skills"]["write_approval"] = True
    cfg.save_config(config)
    importlib.reload(smt)

    # An existing skill already in the library (write approval would stage a
    # tool-driven create, so place it on disk directly).
    existing = jettstui_home / "skills" / "reliable-tests"
    existing.mkdir(parents=True)
    (existing / "SKILL.md").write_text(GOOD, encoding="utf-8")

    paraphrase = GOOD.replace("name: reliable-tests", "name: verified-tests-for-code-changes")
    token = set_current_write_origin("background_review")
    try:
        result = json.loads(
            smt.skill_manage("create", "verified-tests-for-code-changes", content=paraphrase)
        )
    finally:
        reset_current_write_origin(token)

    assert result["success"] is False
    assert "reliable-tests" in result["error"]
    assert wa.pending_count("skills") == 0

