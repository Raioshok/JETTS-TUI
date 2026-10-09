from pathlib import Path

from jettstui.cli_commands_mixin import CLICommandsMixin
from jettstui.commands import resolve_command
from jettstui.specs import run_spec_command


def test_new_spec_creates_exactly_three_documents(tmp_path: Path):
    result = run_spec_command("new Offline Search", tmp_path)
    spec = tmp_path / ".jettstui" / "specs" / "offline-search"

    assert result.requested_mode == "plan"
    assert result.agent_seed
    assert sorted(path.name for path in spec.iterdir()) == [
        "design.md",
        "requirements.md",
        "tasks.md",
    ]
    assert "status: draft" in (spec / "requirements.md").read_text(encoding="utf-8")


def test_spec_approval_enforces_requirements_design_tasks_order(tmp_path: Path):
    run_spec_command("new Offline Search", tmp_path)

    blocked = run_spec_command("approve offline-search design", tmp_path)
    assert "Approve requirements.md" in blocked.text

    requirements = run_spec_command("approve offline-search requirements", tmp_path)
    assert requirements.agent_seed
    assert "status: approved" in (
        tmp_path / ".jettstui/specs/offline-search/requirements.md"
    ).read_text(encoding="utf-8")

    design = run_spec_command("approve offline-search design", tmp_path)
    assert design.agent_seed
    tasks = run_spec_command("approve offline-search tasks", tmp_path)
    assert tasks.agent_seed is None
    assert "/mode accept-edits" in tasks.text


def test_implement_requires_approved_tasks_and_switches_mode(tmp_path: Path):
    run_spec_command("new Offline Search", tmp_path)
    denied = run_spec_command("implement offline-search", tmp_path)
    assert "Approve the task list" in denied.text

    run_spec_command("approve offline-search requirements", tmp_path)
    run_spec_command("approve offline-search design", tmp_path)
    run_spec_command("approve offline-search tasks", tmp_path)
    ready = run_spec_command("implement offline-search", tmp_path)
    assert ready.requested_mode == "accept-edits"
    assert "requirements.md, design.md, and tasks.md" in ready.agent_seed


def test_quick_spec_seeds_all_three_documents(tmp_path: Path):
    result = run_spec_command("quick Offline Search", tmp_path)

    assert result.requested_mode == "plan"
    assert result.agent_seed
    assert "Quick Spec" in result.agent_seed
    assert "tasks.md" in result.agent_seed


def test_legacy_tasklist_remains_approvable(tmp_path: Path):
    run_spec_command("new Offline Search", tmp_path)
    spec = tmp_path / ".jettstui" / "specs" / "offline-search"
    (spec / "tasklist.md").write_text((spec / "tasks.md").read_text(encoding="utf-8"), encoding="utf-8")
    (spec / "tasks.md").unlink()

    run_spec_command("approve offline-search requirements", tmp_path)
    run_spec_command("approve offline-search design", tmp_path)
    result = run_spec_command("approve offline-search tasks", tmp_path)

    assert result.requested_mode is None
    assert "status: approved" in (spec / "tasklist.md").read_text(encoding="utf-8")


def test_status_lists_each_stage(tmp_path: Path):
    run_spec_command("new Offline Search", tmp_path)
    status = run_spec_command("status offline-search", tmp_path)
    assert "requirements" in status.text
    assert "design" in status.text
    assert "tasks" in status.text


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
