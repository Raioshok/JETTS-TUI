"""Kiro-style spec-driven development.

Specs follow Kiro's layout and workflow so a repository can move between Kiro
and JettsTUI without conversion::

    .kiro/specs/<feature-name>/
    ├── .config.kiro        {"specId", "workflowType", "specType"}
    ├── requirements.md     user stories + EARS acceptance criteria
    ├── design.md           architecture, interfaces, correctness properties
    └── tasks.md            checkbox implementation plan

Documents appear one phase at a time, exactly like Kiro: the agent writes
``requirements.md``; when the user approves it the agent writes ``design.md``;
approving that produces ``tasks.md``.  The phase is read from which documents
exist — there is no status bookkeeping inside the files.  Tasks are executed
one at a time ("Start task") or in order ("Run all tasks"), and the agent
tracks progress in the checkboxes: ``[ ]`` not started, ``[-]`` in progress,
``[x]`` done.  ``[ ]*`` marks an optional task (Kiro's optional tests), which
"Run all" skips.

Steering documents in ``.kiro/steering/`` are read before drafting.  Specs
created by older JettsTUI versions under ``.jettstui/specs/`` (with
``status:`` frontmatter) keep working.
"""

from __future__ import annotations

import json
import re
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from utils import atomic_replace


SPEC_ROOT = Path(".kiro") / "specs"
LEGACY_SPEC_ROOT = Path(".jettstui") / "specs"
STEERING_DIR = Path(".kiro") / "steering"
CONFIG_FILE = ".config.kiro"

STAGES: Tuple[str, ...] = ("requirements", "design", "tasks")
STAGE_FILES = {
    "requirements": "requirements.md",
    "design": "design.md",
    "tasks": "tasks.md",
    "tasklist": "tasklist.md",
    "tasks-legacy": "tasklist.md",
}
_STAGE_ALIASES = {"req": "requirements", "requirement": "requirements", "tasklist": "tasks", "task": "tasks"}

# Phase of a spec, in workflow order.
PHASES: Tuple[str, ...] = ("requirements", "design", "tasks", "implementation", "done")


@dataclass(frozen=True)
class SpecCommandResult:
    text: str
    agent_seed: Optional[str] = None
    active_spec: Optional[str] = None
    requested_mode: Optional[str] = None


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (slug[:64].rstrip("-") or "feature-spec")


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", delete=False, dir=path.parent,
        prefix=f".{path.name}.", suffix=".tmp",
    ) as handle:
        handle.write(content)
        tmp = Path(handle.name)
    atomic_replace(tmp, path)


# ─── Tasks ──────────────────────────────────────────────────────────────────

_TASK_RE = re.compile(
    r"^(?P<indent>[ \t]*)[-*] \[(?P<mark>[ xX\-~])\](?P<optional>\*)?\s+"
    r"(?P<id>\d+(?:\.\d+)*)\.?\s+(?P<title>.+?)\s*$"
)
_REQ_REF_RE = re.compile(r"_?Requirements?:\s*([^_\n]+)_?", re.IGNORECASE)
_STATUS_BY_MARK = {" ": "not_started", "-": "in_progress", "~": "queued", "x": "completed", "X": "completed"}


@dataclass
class SpecTask:
    id: str
    title: str
    status: str
    optional: bool
    depth: int
    line: int
    details: List[str] = field(default_factory=list)
    requirements: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def parse_tasks(text: str) -> List[SpecTask]:
    """Kiro task list → tasks with id, status, optional flag and details."""
    tasks: List[SpecTask] = []
    for lineno, raw in enumerate(text.splitlines()):
        match = _TASK_RE.match(raw)
        if match:
            task_id = match.group("id")
            tasks.append(SpecTask(
                id=task_id,
                title=match.group("title"),
                status=_STATUS_BY_MARK[match.group("mark")],
                optional=bool(match.group("optional")),
                depth=task_id.count("."),
                line=lineno,
            ))
            continue
        if tasks and raw.strip() and raw[:1] in (" ", "\t"):
            detail = raw.strip().lstrip("-*").strip()
            ref = _REQ_REF_RE.search(detail)
            if ref:
                tasks[-1].requirements.extend(
                    part.strip() for part in ref.group(1).split(",") if part.strip()
                )
            elif detail:
                tasks[-1].details.append(detail)
    return tasks


def _leaf_tasks(tasks: List[SpecTask]) -> List[SpecTask]:
    ids = {t.id for t in tasks}
    return [t for t in tasks if not any(other.startswith(t.id + ".") for other in ids)]


def task_progress(tasks: List[SpecTask]) -> dict:
    required = [t for t in _leaf_tasks(tasks) if not t.optional]
    return {
        "total": len(required),
        "completed": sum(1 for t in required if t.status == "completed"),
        "in_progress": sum(1 for t in required if t.status == "in_progress"),
        "optional": sum(1 for t in _leaf_tasks(tasks) if t.optional),
    }


def next_task(tasks: List[SpecTask], include_optional: bool = False) -> Optional[SpecTask]:
    for task in _leaf_tasks(tasks):
        if task.status != "completed" and (include_optional or not task.optional):
            return task
    return None


# ─── Locating specs ─────────────────────────────────────────────────────────


def _spec_dirs(cwd: Path) -> List[Path]:
    out: List[Path] = []
    seen = set()
    for root in (cwd / SPEC_ROOT, cwd / LEGACY_SPEC_ROOT):
        if not root.is_dir():
            continue
        for item in sorted(root.iterdir()):
            if item.is_dir() and not item.name.startswith(".") and item.name not in seen:
                seen.add(item.name)
                out.append(item)
    return out


def _resolve(cwd: Path, name: str) -> Optional[Path]:
    if not name:
        return None
    slug = slugify(name)
    for root in (cwd / SPEC_ROOT, cwd / LEGACY_SPEC_ROOT):
        if (root / slug).is_dir():
            return root / slug
    matches = [item for item in _spec_dirs(cwd) if item.name.startswith(slug)]
    return matches[0] if len(matches) == 1 else None


def _is_legacy(spec: Path) -> bool:
    return spec.parent.parent.name == ".jettstui"


def _tasks_filename(spec: Path) -> str:
    """Kiro's tasks.md, with the legacy tasklist.md fallback."""
    if (spec / "tasks.md").exists() or not (spec / "tasklist.md").exists():
        return "tasks.md"
    return "tasklist.md"


def _doc_path(spec: Path, stage: str) -> Path:
    return spec / (_tasks_filename(spec) if stage == "tasks" else STAGE_FILES[stage])


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _legacy_status(path: Path) -> str:
    match = re.search(r"(?m)^status:\s*([\w-]+)\s*$", _read(path))
    return match.group(1) if match else ""


def _has_doc(spec: Path, stage: str) -> bool:
    """A document counts once it exists with content.

    Legacy specs pre-created every file from a template, so there a stage only
    counts once the previous stage was approved in its frontmatter (or it is the
    requirements file itself).
    """
    path = _doc_path(spec, stage)
    if not path.exists() or not _read(path).strip():
        return False
    if _is_legacy(spec) and stage != "requirements":
        previous = STAGES[STAGES.index(stage) - 1]
        return _legacy_status(_doc_path(spec, previous)) == "approved"
    return True


def spec_phase(spec: Path) -> str:
    if _has_doc(spec, "tasks"):
        progress = task_progress(parse_tasks(_read(_doc_path(spec, "tasks"))))
        if progress["total"] and progress["completed"] == progress["total"]:
            return "done"
        if progress["completed"] or progress["in_progress"]:
            return "implementation"
        return "tasks"
    if _has_doc(spec, "design"):
        return "design"
    return "requirements"


def _spec_config(spec: Path) -> dict:
    try:
        data = json.loads(_read(spec / CONFIG_FILE) or "{}")
    except ValueError:
        data = {}
    return data if isinstance(data, dict) else {}


def spec_summary(spec: Path) -> dict:
    tasks = parse_tasks(_read(_doc_path(spec, "tasks"))) if _has_doc(spec, "tasks") else []
    config = _spec_config(spec)
    return {
        "name": spec.name,
        "path": str(spec),
        "legacy": _is_legacy(spec),
        "spec_type": str(config.get("specType") or "feature"),
        "workflow_type": str(config.get("workflowType") or "requirements-first"),
        "phase": spec_phase(spec),
        "documents": {stage: _has_doc(spec, stage) for stage in STAGES},
        "progress": task_progress(tasks),
    }


def spec_detail(spec: Path) -> dict:
    """Everything a UI needs: summary, document text and parsed tasks."""
    detail = spec_summary(spec)
    detail["files"] = {stage: str(_doc_path(spec, stage)) for stage in STAGES}
    detail["content"] = {stage: _read(_doc_path(spec, stage)) if detail["documents"][stage] else "" for stage in STAGES}
    detail["tasks"] = [t.to_dict() for t in parse_tasks(detail["content"]["tasks"])]
    nxt = next_task(parse_tasks(detail["content"]["tasks"]))
    detail["next_task"] = nxt.id if nxt else None
    return detail


def list_spec_summaries(cwd: Path) -> List[dict]:
    return [spec_summary(spec) for spec in _spec_dirs(cwd)]


def find_spec(cwd: Path, name: str) -> Optional[Path]:
    return _resolve(cwd, name)


# ─── Agent prompts (Kiro's workflow) ────────────────────────────────────────


def _rel(spec: Path, filename: str = "") -> str:
    root = ".jettstui/specs" if _is_legacy(spec) else ".kiro/specs"
    return f"{root}/{spec.name}/{filename}" if filename else f"{root}/{spec.name}/"


_STEERING = (
    "If `.kiro/steering/` exists, read its steering documents first and follow "
    "them. Inspect the repository with read-only tools to ground every statement "
    "in the real code."
)

_REQUIREMENTS_FORMAT = """Use exactly this format:

# Requirements Document

## Introduction

<the feature, its users, scope and the outcome it delivers>

## Glossary

- **<Term>**: <definition> (name the system under specification here)

## Requirements

### Requirement 1

**User Story:** As a <role>, I want <capability>, so that <benefit>

#### Acceptance Criteria

1. WHEN <trigger>, THE <System> SHALL <response>
2. IF <unwanted condition>, THEN THE <System> SHALL <response>

Write every acceptance criterion in EARS form — ubiquitous (THE <System> SHALL),
event-driven (WHEN), state-driven (WHILE), unwanted behaviour (IF … THEN) or
optional feature (WHERE) — so each one is individually testable. Cover edge
cases, error handling, user experience and technical constraints."""

_DESIGN_FORMAT = """Use exactly these sections:

# Design Document

## Overview
## Architecture            (Mermaid diagrams where they help)
## Components and Interfaces
## Data Models
## Correctness Properties  (properties that must hold for all inputs, each
                            tagged with the acceptance criteria it validates,
                            e.g. "Validates: Requirements 1.2, 3.1"; these
                            drive property-based tests)
## Error Handling
## Testing Strategy

Research what the design depends on, explain the key decisions and their
rationale, and make sure every requirement is addressed."""

_TASKS_FORMAT = """Use exactly this format:

# Implementation Plan

- [ ] 1. <Set up the core structure>
  - <what to build, which files>
  - _Requirements: 1.1, 2.3_

- [ ] 2. <Next capability>
- [ ] 2.1 <Sub-task>
  - <details>
  - _Requirements: 2.1_
- [ ]* 2.2 <Optional test task, e.g. write property tests for property 3>
  - _Requirements: 2.1_

Turn the design into a series of prompts for a code-generation agent that
implements each step incrementally and test-driven: every task builds on the
previous ones and ends wired in, with no orphaned code. At most two levels
(epics and sub-tasks), numbered 1, 2, 2.1, …. Each task references the
acceptance criteria it satisfies. Only coding tasks — writing, modifying or
testing code; no deployment, user testing or metrics gathering. Mark optional
tasks (typically extra tests) with `*` after the checkbox."""


def _review_question(spec: Path, stage: str, next_step: str) -> str:
    return (
        f"When the document is written, ask the user: \"Does the {stage} look good? "
        f"If so, we can move on to {next_step}.\" Then stop and wait. They approve "
        f"with `/spec approve {spec.name} {stage}` or ask for changes with "
        f"`/spec refine {spec.name} {stage} <feedback>`."
    )


def _requirements_seed(spec: Path, feature: str) -> str:
    return "\n\n".join([
        f"You are in the REQUIREMENTS phase of the spec for '{feature}'. Write "
        f"`{_rel(spec, 'requirements.md')}`.",
        _STEERING,
        _REQUIREMENTS_FORMAT,
        "Do not write the design or tasks yet and do not change any code.",
        _review_question(spec, "requirements", "the design"),
    ])


def _design_seed(spec: Path) -> str:
    return "\n\n".join([
        f"The requirements in `{_rel(spec, 'requirements.md')}` are approved. You are "
        f"in the DESIGN phase: write `{_rel(spec, 'design.md')}`.",
        _STEERING,
        _DESIGN_FORMAT,
        "Do not write tasks yet and do not change any code.",
        _review_question(spec, "design", "the implementation plan"),
    ])


def _tasks_seed(spec: Path) -> str:
    return "\n\n".join([
        f"The design in `{_rel(spec, 'design.md')}` is approved. You are in the TASKS "
        f"phase: read requirements.md and design.md, then write `{_rel(spec, 'tasks.md')}`.",
        _TASKS_FORMAT,
        "Do not implement anything yet.",
        _review_question(spec, "tasks", "implementation"),
    ])


_TASK_RULES = (
    "Rules for every task: before starting it, change its checkbox to `[-]`; "
    "implement it, keeping to the design; verify it against the acceptance "
    "criteria it references, running the relevant tests; only when verification "
    "passes change its checkbox to `[x]`. When all sub-tasks of a task are `[x]`, "
    "mark the parent `[x]` too. Preserve unrelated user changes."
)


def _task_seed(spec: Path, task: SpecTask) -> str:
    tasks_file = _tasks_filename(spec)
    sub = " It has sub-tasks: work through them in order." if task.depth == 0 else ""
    return "\n\n".join([
        f"Execute task {task.id} from `{_rel(spec, tasks_file)}`: \"{task.title}\".{sub}",
        f"Read `{_rel(spec, 'requirements.md')}`, `{_rel(spec, 'design.md')}` and "
        f"`{_rel(spec, tasks_file)}` first.",
        _TASK_RULES,
        "Focus on this task only — do not start any other task. When it is done, "
        "stop and summarize what changed so the user can review it.",
    ])


def _run_all_seed(spec: Path, include_optional: bool) -> str:
    tasks_file = _tasks_filename(spec)
    optional = (
        "Include optional tasks marked `*`."
        if include_optional
        else "Skip optional tasks marked `*`."
    )
    return "\n\n".join([
        f"Run all remaining tasks in `{_rel(spec, tasks_file)}`, one at a time in order.",
        f"Read `{_rel(spec, 'requirements.md')}`, `{_rel(spec, 'design.md')}` and "
        f"`{_rel(spec, tasks_file)}` first. {optional}",
        _TASK_RULES,
        "Finish each task completely before the next. If a task cannot be completed "
        "or its verification fails, stop there and report what blocked it. At the "
        "end, summarize every task you completed.",
    ])


def _refine_seed(spec: Path, stage: str, feedback: str) -> str:
    downstream = [s for s in STAGES[STAGES.index(stage) + 1:] if _has_doc(spec, s)]
    later = (
        f" {', '.join(f'{s}.md' for s in downstream)} already exist; after updating, "
        "tell the user which parts of them the change affects and ask before "
        "updating them."
        if downstream else ""
    )
    return "\n\n".join([
        f"Update `{_rel(spec, _doc_path(spec, stage).name)}` with this feedback from the user:",
        feedback.strip(),
        f"Keep the Kiro {stage} format and change nothing else in the repository.{later}",
        _review_question(spec, stage, {
            "requirements": "the design",
            "design": "the implementation plan",
            "tasks": "implementation",
        }[stage]),
    ])


def _auto_seed(spec: Path, feature: str) -> str:
    return "\n\n".join([
        f"Autopilot spec for '{feature}': produce the whole Kiro spec in "
        f"`{_rel(spec)}` and then implement it, without stopping for approvals.",
        _STEERING,
        f"1. Write `{_rel(spec, 'requirements.md')}`.\n{_REQUIREMENTS_FORMAT}",
        f"2. Write `{_rel(spec, 'design.md')}` from the requirements.\n{_DESIGN_FORMAT}",
        f"3. Write `{_rel(spec, 'tasks.md')}` from the design.\n{_TASKS_FORMAT}",
        "4. Execute every required task in order (skip optional `*` tasks). " + _TASK_RULES,
        "If anything is ambiguous, make the most reasonable choice and record it under "
        "an 'Assumptions' heading in requirements.md. Stop and report if a task's "
        "verification fails. End with a summary of the spec and every completed task.",
    ])


# ─── Commands ───────────────────────────────────────────────────────────────


def _create_dir(cwd: Path, feature: str) -> Tuple[Optional[Path], Optional[SpecCommandResult]]:
    slug = slugify(feature)
    existing = _resolve(cwd, slug)
    if existing is not None and existing.name == slug:
        return None, SpecCommandResult(
            f"Spec '{slug}' already exists at {existing}. Use /spec status {slug}.",
            active_spec=slug,
        )
    spec = cwd / SPEC_ROOT / slug
    _atomic_text(spec / CONFIG_FILE, json.dumps({
        "specId": str(uuid.uuid4()),
        "workflowType": "requirements-first",
        "specType": "feature",
    }, indent=2) + "\n")
    return spec, None


def create_spec(cwd: Path, feature: str) -> SpecCommandResult:
    spec, error = _create_dir(cwd, feature)
    if error:
        return error
    return SpecCommandResult(
        f"Created spec: {spec.name}\n  {spec}\nPlan mode enabled; drafting requirements.md next.",
        agent_seed=_requirements_seed(spec, feature),
        active_spec=spec.name,
        requested_mode="plan",
    )


def quick_spec(cwd: Path, feature: str) -> SpecCommandResult:
    """Draft all three documents in one pass, still stopping before code."""
    spec, error = _create_dir(cwd, feature)
    if error:
        return error
    seed = "\n\n".join([
        f"Create a complete Quick Spec for '{feature}' in `{_rel(spec)}`: write "
        "requirements.md, then design.md, then tasks.md in one pass.",
        _STEERING,
        _REQUIREMENTS_FORMAT,
        _DESIGN_FORMAT,
        _TASKS_FORMAT,
        "Do not implement anything. End by asking the user to review the three "
        f"documents; they can start with `/spec task {spec.name} 1` or "
        f"`/spec run {spec.name}`.",
    ])
    return SpecCommandResult(
        f"Created spec: {spec.name}\n  {spec}\nPlan mode enabled; drafting the full quick spec next.",
        agent_seed=seed,
        active_spec=spec.name,
        requested_mode="plan",
    )


def auto_spec(cwd: Path, feature: str) -> SpecCommandResult:
    spec, error = _create_dir(cwd, feature)
    if error:
        return error
    return SpecCommandResult(
        f"Created spec: {spec.name}\n  {spec}\nAutopilot: writing requirements, design and "
        "tasks, then implementing every required task (Accept Edits mode, no approval stops).",
        agent_seed=_auto_seed(spec, feature),
        active_spec=spec.name,
        requested_mode="accept-edits",
    )


def list_specs(cwd: Path) -> SpecCommandResult:
    summaries = list_spec_summaries(cwd)
    if not summaries:
        return SpecCommandResult("No specs yet. Create one with /spec new <feature>.")
    lines = ["Specs:"]
    for item in summaries:
        progress = item["progress"]
        tasks = f"  {progress['completed']}/{progress['total']} tasks" if item["documents"]["tasks"] else ""
        lines.append(f"  {item['name']:<28} {item['phase']}{tasks}")
    return SpecCommandResult("\n".join(lines))


def spec_status(cwd: Path, name: str) -> SpecCommandResult:
    spec = _resolve(cwd, name)
    if spec is None:
        return SpecCommandResult(f"Spec '{name}' was not found.")
    summary = spec_summary(spec)
    lines = [f"Spec: {spec.name}  (phase: {summary['phase']})"]
    for stage in STAGES:
        state = "written" if summary["documents"][stage] else "not yet"
        lines.append(f"  {stage:<12} {state:<8} {_doc_path(spec, stage)}")
    if summary["documents"]["tasks"]:
        tasks = parse_tasks(_read(_doc_path(spec, "tasks")))
        glyph = {"not_started": " ", "in_progress": "-", "queued": "~", "completed": "x"}
        lines.append("")
        for task in tasks:
            lines.append(
                f"  {'  ' * task.depth}[{glyph[task.status]}]{'*' if task.optional else ' '} {task.id} {task.title}"
            )
    return SpecCommandResult("\n".join(lines), active_spec=spec.name)


def _canonical_stage(stage: str) -> str:
    stage = stage.lower()
    return _STAGE_ALIASES.get(stage, stage)


def _approve(cwd: Path, name: str, stage: str) -> SpecCommandResult:
    spec = _resolve(cwd, name)
    stage = _canonical_stage(stage)
    if spec is None or stage not in STAGES:
        return SpecCommandResult("Usage: /spec approve <name> <requirements|design|tasks>")
    if not _has_doc(spec, stage):
        return SpecCommandResult(
            f"There is no {stage} document for '{spec.name}' yet — "
            f"{'wait for it to be written' if stage == 'requirements' else 'approve the previous phase first'}.",
            active_spec=spec.name,
        )
    if _is_legacy(spec):
        target = _doc_path(spec, stage)
        updated, count = re.subn(r"(?m)^status:\s*[\w-]+\s*$", "status: approved", _read(target), count=1)
        if count:
            _atomic_text(target, updated)

    if stage == "requirements":
        return SpecCommandResult(
            f"Requirements approved for '{spec.name}'. Drafting design.md next.",
            agent_seed=_design_seed(spec), active_spec=spec.name, requested_mode="plan",
        )
    if stage == "design":
        return SpecCommandResult(
            f"Design approved for '{spec.name}'. Drafting tasks.md next.",
            agent_seed=_tasks_seed(spec), active_spec=spec.name, requested_mode="plan",
        )
    return SpecCommandResult(
        f"Task list approved — '{spec.name}' is ready. Start one task with "
        f"`/spec task {spec.name} <id>` or all of them with `/spec run {spec.name}`.",
        active_spec=spec.name,
    )


def _refine(cwd: Path, name: str, stage: str, feedback: str) -> SpecCommandResult:
    spec = _resolve(cwd, name)
    stage = _canonical_stage(stage)
    if spec is None or stage not in STAGES or not feedback.strip():
        return SpecCommandResult("Usage: /spec refine <name> <requirements|design|tasks> <feedback>")
    if not _has_doc(spec, stage):
        return SpecCommandResult(f"There is no {stage} document for '{spec.name}' yet.", active_spec=spec.name)
    return SpecCommandResult(
        f"Updating {stage} for '{spec.name}'.",
        agent_seed=_refine_seed(spec, stage, feedback), active_spec=spec.name, requested_mode="plan",
    )


def _start_task(cwd: Path, name: str, task_id: str) -> SpecCommandResult:
    spec = _resolve(cwd, name)
    if spec is None:
        return SpecCommandResult(f"Spec '{name}' was not found.")
    if not _has_doc(spec, "tasks"):
        return SpecCommandResult(f"'{spec.name}' has no task list yet.", active_spec=spec.name)
    tasks = parse_tasks(_read(_doc_path(spec, "tasks")))
    task = next((t for t in tasks if t.id == task_id.rstrip(".")), None) if task_id else next_task(tasks)
    if task is None:
        return SpecCommandResult(
            f"Task '{task_id}' was not found in '{spec.name}'." if task_id else f"Every task in '{spec.name}' is done.",
            active_spec=spec.name,
        )
    if task.status == "completed":
        return SpecCommandResult(f"Task {task.id} is already complete.", active_spec=spec.name)
    return SpecCommandResult(
        f"Starting task {task.id} of '{spec.name}': {task.title}",
        agent_seed=_task_seed(spec, task), active_spec=spec.name, requested_mode="accept-edits",
    )


def _run_all(cwd: Path, name: str, include_optional: bool) -> SpecCommandResult:
    spec = _resolve(cwd, name)
    if spec is None:
        return SpecCommandResult(f"Spec '{name}' was not found.")
    if not _has_doc(spec, "tasks"):
        return SpecCommandResult(f"'{spec.name}' has no task list yet.", active_spec=spec.name)
    if next_task(parse_tasks(_read(_doc_path(spec, "tasks"))), include_optional) is None:
        return SpecCommandResult(f"Every task in '{spec.name}' is done.", active_spec=spec.name)
    return SpecCommandResult(
        f"Running all remaining tasks of '{spec.name}' in Accept Edits mode.",
        agent_seed=_run_all_seed(spec, include_optional), active_spec=spec.name, requested_mode="accept-edits",
    )


USAGE = (
    "Usage: /spec [list | new <feature> | quick <feature> | auto <feature> | status <name> | "
    "approve <name> <requirements|design|tasks> | refine <name> <stage> <feedback> | "
    "task <name> [id] | run <name> [--optional]]"
)


def run_spec_command(args: str, cwd: Path, active_spec: Optional[str] = None) -> SpecCommandResult:
    tokens = args.strip().split()
    if not tokens:
        return list_specs(cwd)
    command = tokens[0].lower()
    rest = tokens[1:]

    def named(index: int = 0) -> str:
        return rest[index] if len(rest) > index else (active_spec or "")

    if command in {"new", "create"}:
        feature = " ".join(rest).strip()
        return create_spec(cwd, feature) if feature else SpecCommandResult("Usage: /spec new <feature description>")
    if command in {"quick", "quick-spec", "quick_spec"}:
        feature = " ".join(rest).strip()
        return quick_spec(cwd, feature) if feature else SpecCommandResult("Usage: /spec quick <feature description>")
    if command in {"auto", "autopilot"}:
        feature = " ".join(rest).strip()
        return auto_spec(cwd, feature) if feature else SpecCommandResult("Usage: /spec auto <feature description>")
    if command == "list":
        return list_specs(cwd)
    if command in {"status", "show"}:
        name = " ".join(rest).strip() or active_spec or ""
        return spec_status(cwd, name) if name else SpecCommandResult("Usage: /spec status <name>")
    if command == "approve":
        return _approve(cwd, named(0), rest[1] if len(rest) > 1 else "")
    if command in {"refine", "change", "update"}:
        return _refine(cwd, named(0), rest[1] if len(rest) > 1 else "", " ".join(rest[2:]))
    if command in {"task", "start"}:
        return _start_task(cwd, named(0), rest[1] if len(rest) > 1 else "")
    if command in {"run", "run-all", "implement"}:
        include_optional = "--optional" in rest
        names = [r for r in rest if r != "--optional"]
        return _run_all(cwd, names[0] if names else (active_spec or ""), include_optional)
    return SpecCommandResult(USAGE)
