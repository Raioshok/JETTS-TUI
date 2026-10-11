import json
from pathlib import Path

from jettstui.cli_commands_mixin import CLICommandsMixin
from jettstui.commands import resolve_command
from jettstui.specs import list_spec_summaries, parse_tasks, run_spec_command, spec_detail

SPEC = Path(".kiro") / "specs" / "offline-search"

TASKS = """# Implementation Plan

- [x] 1. Set up the search index
  - Create `search/index.py`
  - _Requirements: 1.1_

- [ ] 2. Query support
- [-] 2.1 Parse queries
  - _Requirements: 1.2, 2.1_
- [ ] 2.2 Rank results
  - _Requirements: 2.2_
- [ ]* 2.3 Write property tests for ranking
  - _Requirements: 2.2_
"""


def _write(root: Path, name: str, text: str = "# doc\n") -> Path:
    path = root / SPEC / name
    path.write_text(text, encoding="utf-8")
    return path


def test_new_spec_is_a_kiro_spec_that_starts_with_requirements(tmp_path: Path):
    result = run_spec_command("new Offline Search", tmp_path)
    spec = tmp_path / SPEC

    assert result.requested_mode == "plan"
    assert "requirements.md" in result.agent_seed
    assert "EARS" in result.agent_seed and "User Story" in result.agent_seed
    # Kiro writes documents one phase at a time; only the config exists up front.
    assert sorted(p.name for p in spec.iterdir()) == [".config.kiro"]
    config = json.loads((spec / ".config.kiro").read_text(encoding="utf-8"))
    assert config["workflowType"] == "requirements-first" and config["specType"] == "feature"
    assert config["specId"]


def test_phase_follows_which_documents_exist(tmp_path: Path):
    run_spec_command("new Offline Search", tmp_path)
    phase = lambda: list_spec_summaries(tmp_path)[0]["phase"]  # noqa: E731

    assert phase() == "requirements"
    _write(tmp_path, "requirements.md")
    _write(tmp_path, "design.md")
    assert phase() == "design"
    _write(tmp_path, "tasks.md", TASKS.replace("[x]", "[ ]").replace("[-]", "[ ]"))
    assert phase() == "tasks"
    _write(tmp_path, "tasks.md", TASKS)
    assert phase() == "implementation"
    _write(tmp_path, "tasks.md", TASKS.replace("[ ] 2.", "[x] 2.").replace("[-]", "[x]"))
    assert phase() == "done"  # optional tasks don't block completion


def test_approval_moves_to_the_next_phase_only_once_the_document_exists(tmp_path: Path):
    run_spec_command("new Offline Search", tmp_path)

    early = run_spec_command("approve offline-search requirements", tmp_path)
    assert early.agent_seed is None and "no requirements" in early.text.lower()
    assert run_spec_command("approve offline-search design", tmp_path).agent_seed is None

    _write(tmp_path, "requirements.md")
    design = run_spec_command("approve offline-search requirements", tmp_path)
    assert "design.md" in design.agent_seed and "Correctness Properties" in design.agent_seed

    _write(tmp_path, "design.md")
    tasks = run_spec_command("approve offline-search design", tmp_path)
    assert "tasks.md" in tasks.agent_seed and "_Requirements:" in tasks.agent_seed

    _write(tmp_path, "tasks.md", TASKS)
    ready = run_spec_command("approve offline-search tasks", tmp_path)
    assert ready.agent_seed is None and "/spec task" in ready.text


def test_parse_tasks_reads_kiro_checkboxes():
    tasks = {t.id: t for t in parse_tasks(TASKS)}
    assert [t for t in tasks] == ["1", "2", "2.1", "2.2", "2.3"]
    assert tasks["1"].status == "completed"
    assert tasks["2.1"].status == "in_progress"
    assert tasks["2.2"].status == "not_started"
    assert tasks["2.3"].optional and not tasks["2.2"].optional
    assert tasks["2.1"].requirements == ["1.2", "2.1"]
    assert tasks["1"].details == ["Create `search/index.py`"]
    assert tasks["2.1"].depth == 1 and tasks["2"].depth == 0


def test_start_task_runs_exactly_one_task_in_accept_edits(tmp_path: Path):
    run_spec_command("new Offline Search", tmp_path)
    _write(tmp_path, "tasks.md", TASKS)

    result = run_spec_command("task offline-search 2.2", tmp_path)
    assert result.requested_mode == "accept-edits"
    assert "task 2.2" in result.agent_seed and "Rank results" in result.agent_seed
    assert "`[-]`" in result.agent_seed and "`[x]`" in result.agent_seed
    assert "do not start any other task" in result.agent_seed

    # Without an id it picks the next unfinished required task.
    assert "task 2.1" in run_spec_command("task offline-search", tmp_path).agent_seed
    assert run_spec_command("task offline-search 1", tmp_path).agent_seed is None  # already done


def test_run_all_skips_optional_tasks_unless_asked(tmp_path: Path):
    run_spec_command("new Offline Search", tmp_path)
    _write(tmp_path, "tasks.md", TASKS)

    run = run_spec_command("run offline-search", tmp_path)
    assert run.requested_mode == "accept-edits" and "Skip optional" in run.agent_seed
    assert "Include optional" in run_spec_command("run offline-search --optional", tmp_path).agent_seed
    # `implement` stays as the old spelling of run-all.
    assert run_spec_command("implement offline-search", tmp_path).agent_seed == run.agent_seed


def test_refine_carries_feedback_and_flags_downstream_documents(tmp_path: Path):
    run_spec_command("new Offline Search", tmp_path)
    _write(tmp_path, "requirements.md")
    _write(tmp_path, "design.md")

    result = run_spec_command("refine offline-search requirements add fuzzy matching", tmp_path)
    assert "add fuzzy matching" in result.agent_seed
    assert "design.md" in result.agent_seed  # downstream doc called out
    assert result.requested_mode == "plan"


def test_auto_runs_the_whole_workflow_in_accept_edits(tmp_path: Path):
    result = run_spec_command("auto Offline Search", tmp_path)
    assert result.requested_mode == "accept-edits"
    for doc in ("requirements.md", "design.md", "tasks.md"):
        assert doc in result.agent_seed
    assert "without stopping for approvals" in result.agent_seed


def test_quick_spec_drafts_all_three_documents_without_code(tmp_path: Path):
    result = run_spec_command("quick Offline Search", tmp_path)
    assert result.requested_mode == "plan"
    assert "Quick Spec" in result.agent_seed and "Do not implement" in result.agent_seed


def test_detail_exposes_documents_and_tasks(tmp_path: Path):
    run_spec_command("new Offline Search", tmp_path)
    _write(tmp_path, "requirements.md", "# Requirements Document\n")
    _write(tmp_path, "tasks.md", TASKS)
    _write(tmp_path, "design.md")

    detail = spec_detail(tmp_path / SPEC)
    assert detail["content"]["requirements"].startswith("# Requirements Document")
    assert detail["next_task"] == "2.1"
    assert detail["progress"] == {"total": 3, "completed": 1, "in_progress": 1, "optional": 1}
    json.dumps(detail)


def test_legacy_jettstui_specs_keep_working(tmp_path: Path):
    legacy = tmp_path / ".jettstui" / "specs" / "old-feature"
    legacy.mkdir(parents=True)
    for name, status in (("requirements.md", "draft"), ("design.md", "draft"), ("tasklist.md", "draft")):
        (legacy / name).write_text(f"---\nstatus: {status}\n---\n# {name}\n", encoding="utf-8")

    # Pre-created template files don't count until the previous stage is approved.
    assert list_spec_summaries(tmp_path)[0]["phase"] == "requirements"
    assert run_spec_command("approve old-feature requirements", tmp_path).agent_seed
    assert "status: approved" in (legacy / "requirements.md").read_text(encoding="utf-8")
    assert list_spec_summaries(tmp_path)[0]["phase"] == "design"
    assert ".jettstui/specs/old-feature/design.md" in run_spec_command(
        "approve old-feature design", tmp_path
    ).agent_seed


def test_status_shows_documents_and_task_checkboxes(tmp_path: Path):
    run_spec_command("new Offline Search", tmp_path)
    _write(tmp_path, "requirements.md")
    _write(tmp_path, "design.md")
    _write(tmp_path, "tasks.md", TASKS)
    status = run_spec_command("status offline-search", tmp_path).text
    assert "implementation" in status
    assert "[-]  2.1 Parse queries" in status
    assert "[ ]* 2.3" in status


def test_existing_spec_is_not_recreated(tmp_path: Path):
    run_spec_command("new Offline Search", tmp_path)
    again = run_spec_command("new Offline Search", tmp_path)
    assert again.agent_seed is None and "already exists" in again.text


def test_registry_exposes_spec_and_mode_commands():
    assert resolve_command("spec").name == "spec"
    assert resolve_command("mode").name == "mode"
    assert resolve_command("permissions").name == "permissions"
    assert resolve_command("perms").name == "permissions"
    assert resolve_command("review").name == "review"
    assert resolve_command("doctor").name == "doctor"


def test_cli_spec_handler_queues_seed_and_enters_plan(tmp_path: Path, monkeypatch):
    class Stub(CLICommandsMixin):
        def __init__(self):
            self.agent = None
            self._active_spec_slug = None
            self._pending_agent_seed = None
            self.output = []

        def _console_print(self, value):
            self.output.append(value)

    monkeypatch.chdir(tmp_path)
    cli = Stub()
    cli._handle_spec_command("/spec new Offline Search")
    assert cli._work_mode == "plan"
    assert cli._active_spec_slug == "offline-search"
    assert cli._pending_agent_seed
