import json

from tools.work_mode import (
    decorate_user_message,
    maybe_block_tool,
    next_mode,
    set_current_work_mode,
)


def test_plan_mode_blocks_code_edits_and_terminal():
    set_current_work_mode("plan")
    edit = json.loads(maybe_block_tool("write_file", {"path": "src/app.py"}))
    terminal = json.loads(maybe_block_tool("terminal", {"command": "pytest"}))
    assert "Plan mode blocked" in edit["error"]
    assert "Plan mode blocked" in terminal["error"]


def test_plan_mode_allows_reads_and_planning_documents():
    set_current_work_mode("plan")
    assert maybe_block_tool("read_file", {"path": "src/app.py"}) is None
    assert maybe_block_tool(
        "write_file", {"path": ".freeide/specs/login/design.md"}
    ) is None
    assert maybe_block_tool(
        "patch", {"mode": "replace", "path": ".freeide/plans/login.md"}
    ) is None
    traversal = maybe_block_tool(
        "write_file", {"path": ".freeide/specs/../../src/app.py"}
    )
    assert "Plan mode blocked" in json.loads(traversal)["error"]


def test_default_and_accept_edits_do_not_add_a_guard():
    for mode in ("default", "accept-edits"):
        set_current_work_mode(mode)
        assert maybe_block_tool("write_file", {"path": "src/app.py"}) is None


def test_mode_directive_is_turn_suffix_content():
    assert decorate_user_message("Build it", "default") == "Build it"
    plan = decorate_user_message("Build it", "plan")
    assert plan.endswith("Build it")
    assert "WORK MODE: PLAN" in plan


def test_mode_cycle_matches_shift_tab_order():
    assert next_mode("default") == "accept-edits"
    assert next_mode("accept-edits") == "plan"
    assert next_mode("plan") == "default"
    assert next_mode("unknown") == "accept-edits"
