"""Kiro-style three-document feature specs for the interactive CLI."""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from utils import atomic_replace


SPEC_ROOT = Path(".jettstui") / "specs"
STAGE_FILES = {
    "requirements": "requirements.md",
    "design": "design.md",
    "tasks": "tasks.md",
    "tasklist": "tasklist.md",
    "tasks-legacy": "tasklist.md",
}


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


def _frontmatter(slug: str, stage: str, status: str = "draft") -> str:
    return f"---\nspec: {slug}\nstage: {stage}\nstatus: {status}\n---\n"


def _templates(slug: str, feature: str) -> dict[str, str]:
    return {
        "requirements.md": _frontmatter(slug, "requirements") + f"""
# Requirements: {feature}

## Introduction

Describe the problem, intended users, scope, and measurable outcome.

## Glossary

- **System**: The feature or product being specified.

## Requirements

### Requirement 1 — Core outcome

**User story:** As a user, I want {feature}, so that the intended outcome is achieved.

#### Acceptance criteria

1. WHEN the primary workflow is used, THE System SHALL produce the expected result.
2. IF invalid input is supplied, THEN THE System SHALL return an actionable error.
3. THE System SHALL preserve existing compatible behavior.

## Out of scope

- Record explicit non-goals here.

## Open questions

- Resolve unknown product decisions before approving this document.
""".lstrip(),
        "design.md": _frontmatter(slug, "design") + f"""
# Technical Design: {feature}

> Complete after `requirements.md` is approved.

## Overview

## Current architecture

## Proposed architecture

## Components and interfaces

## Data model

## Error handling

## Security and privacy

## Testing strategy

## Alternatives considered

## Risks and mitigations
""".lstrip(),
        "tasks.md": _frontmatter(slug, "tasks") + f"""
# Implementation Task List: {feature}

> Complete after `design.md` is approved. Every task must reference a requirement.

- [ ] 1. Add failing behavior tests
  - Files: `path/to/test_file`
  - Requirements: 1
  - Verify: exact command and expected failure
- [ ] 2. Implement the smallest compliant change
  - Files: `path/to/source_file`
  - Requirements: 1
  - Verify: exact command and expected pass
- [ ] 3. Run integration and regression checks
  - Requirements: 1
  - Verify: exact commands and expected results
""".lstrip(),
    }


def create_spec(cwd: Path, feature: str) -> SpecCommandResult:
    slug = slugify(feature)
    spec_dir = cwd / SPEC_ROOT / slug
    if spec_dir.exists():
        return SpecCommandResult(
            f"Spec '{slug}' already exists at {spec_dir}. Use /spec status {slug}.",
            active_spec=slug,
        )
    for filename, content in _templates(slug, feature).items():
        _atomic_text(spec_dir / filename, content)
    seed = (
        f"Create the requirements stage for feature '{feature}' in "
        f"`.jettstui/specs/{slug}/requirements.md`. Inspect the repository with "
        "read-only tools, replace generic placeholders with concrete EARS-style "
        "requirements and testable acceptance criteria, and preserve the YAML "
        "frontmatter status as draft. Do not implement code and do not author the "
        "technical design yet. End by asking the user to review it and run "
        f"`/spec approve {slug} requirements`."
    )
    return SpecCommandResult(
        "\n".join([
            f"Created spec: {slug}",
            f"  {spec_dir / 'requirements.md'}",
            f"  {spec_dir / 'design.md'}",
            f"  {spec_dir / 'tasks.md'}",
            "Plan mode enabled; drafting requirements next.",
        ]),
        agent_seed=seed,
        active_spec=slug,
        requested_mode="plan",
    )


def quick_spec(cwd: Path, feature: str) -> SpecCommandResult:
    """Create a Kiro-style quick spec and seed all three documents at once."""
    result = create_spec(cwd, feature)
    if not result.agent_seed or not result.active_spec:
        return result
    seed = (
        f"Create a complete Quick Spec for feature '{feature}' in "
        f"`.jettstui/specs/{result.active_spec}/`. Fill requirements.md, design.md, "
        "and tasks.md in one pass with concrete repository-specific content. "
        "Inspect the repository with read-only tools, replace all placeholders, "
        "keep every file status as draft, do not implement code, and end by "
        "asking the user to review the three files and approve them with "
        f"`/spec approve {result.active_spec} requirements`, "
        f"`/spec approve {result.active_spec} design`, and "
        f"`/spec approve {result.active_spec} tasks`."
    )
    return SpecCommandResult(
        result.text.replace("drafting requirements next", "drafting the full quick spec next"),
        agent_seed=seed,
        active_spec=result.active_spec,
        requested_mode="plan",
    )


def _status(path: Path) -> str:
    if not path.exists():
        return "missing"
    match = re.search(r"(?m)^status:\s*([\w-]+)\s*$", path.read_text(encoding="utf-8"))
    return match.group(1) if match else "unknown"


def _resolve(cwd: Path, name: str) -> Optional[Path]:
    root = cwd / SPEC_ROOT
    exact = root / slugify(name)
    if exact.is_dir():
        return exact
    if not root.is_dir():
        return None
    matches = [item for item in root.iterdir() if item.is_dir() and item.name.startswith(slugify(name))]
    return matches[0] if len(matches) == 1 else None


def list_specs(cwd: Path) -> SpecCommandResult:
    root = cwd / SPEC_ROOT
    specs = sorted(item for item in root.iterdir() if item.is_dir()) if root.is_dir() else []
    if not specs:
        return SpecCommandResult("No specs yet. Create one with /spec new <feature>.")
    lines = ["Feature specs:"]
    for spec in specs:
        states = ", ".join(
            f"{stage}={_status(spec / filename)}"
            for stage, filename in (("req", "requirements.md"), ("design", "design.md"), ("tasks", _tasks_filename(spec)))
        )
        lines.append(f"  {spec.name}  [{states}]")
    return SpecCommandResult("\n".join(lines))


def spec_status(cwd: Path, name: str) -> SpecCommandResult:
    spec = _resolve(cwd, name)
    if spec is None:
        return SpecCommandResult(f"Spec '{name}' was not found.")
    lines = [f"Spec: {spec.name}"]
    for stage, filename in (("requirements", "requirements.md"), ("design", "design.md"), ("tasks", _tasks_filename(spec))):
        lines.append(f"  {stage:<12} {_status(spec / filename):<9} {spec / filename}")
    return SpecCommandResult("\n".join(lines), active_spec=spec.name)


def _tasks_filename(spec: Path) -> str:
    """Return the Kiro-compatible tasks filename, with legacy tasklist fallback."""
    if (spec / "tasks.md").exists():
        return "tasks.md"
    return "tasklist.md"


def _approve(cwd: Path, name: str, stage: str) -> SpecCommandResult:
    spec = _resolve(cwd, name)
    canonical_stage = "tasks" if stage == "tasklist" else stage
    filename = STAGE_FILES.get(stage)
    if spec is None or filename is None:
        return SpecCommandResult("Usage: /spec approve <name> <requirements|design|tasks>")
    if canonical_stage == "tasks":
        filename = _tasks_filename(spec)
    prerequisites = {"design": "requirements.md", "tasks": "design.md"}
    required = prerequisites.get(canonical_stage)
    if required and _status(spec / required) != "approved":
        return SpecCommandResult(f"Approve {required} before {filename}.", active_spec=spec.name)
    target = spec / filename
    if not target.exists():
        return SpecCommandResult(f"Missing spec file: {target}", active_spec=spec.name)
    content = target.read_text(encoding="utf-8")
    updated, count = re.subn(r"(?m)^status:\s*[\w-]+\s*$", "status: approved", content, count=1)
    if count != 1:
        return SpecCommandResult(f"Could not find status frontmatter in {target}.", active_spec=spec.name)
    _atomic_text(target, updated)

    if canonical_stage == "requirements":
        seed = (
            f"Requirements for spec '{spec.name}' are approved. Read "
            f"`.jettstui/specs/{spec.name}/requirements.md`, inspect the current "
            "codebase using read-only tools, and complete "
            f"`.jettstui/specs/{spec.name}/design.md` with concrete architecture, "
            "interfaces, data flow, errors, security, alternatives, and tests. "
            "Keep status draft; do not implement. End by requesting "
            f"`/spec approve {spec.name} design`."
        )
        next_text = "Requirements approved; drafting technical design next."
    elif canonical_stage == "design":
        seed = (
            f"Design for spec '{spec.name}' is approved. Read its requirements.md "
            "and design.md, then complete tasks.md with ordered, bite-sized "
            "checkbox tasks. Include exact files, requirement references, tests, "
            "commands, dependencies, and completion criteria. Keep status draft; "
            f"do not implement. End by requesting `/spec approve {spec.name} tasks`."
        )
        next_text = "Design approved; drafting implementation task list next."
    else:
        seed = None
        next_text = (
            "Task list approved. The spec is ready. Switch with "
            f"`/mode accept-edits`, then run `/spec implement {spec.name}`."
        )
    return SpecCommandResult(
        f"Approved {canonical_stage} for '{spec.name}'. {next_text}",
        agent_seed=seed,
        active_spec=spec.name,
        requested_mode="plan" if seed else None,
    )


def run_spec_command(args: str, cwd: Path, active_spec: Optional[str] = None) -> SpecCommandResult:
    tokens = args.strip().split()
    if not tokens:
        return list_specs(cwd)
    command = tokens[0].lower()
    if command in {"new", "create"}:
        feature = " ".join(tokens[1:]).strip()
        return create_spec(cwd, feature) if feature else SpecCommandResult("Usage: /spec new <feature description>")
    if command in {"quick", "quick-spec", "quick_spec"}:
        feature = " ".join(tokens[1:]).strip()
        return quick_spec(cwd, feature) if feature else SpecCommandResult("Usage: /spec quick <feature description>")
    if command == "list":
        return list_specs(cwd)
    if command in {"status", "show"}:
        name = " ".join(tokens[1:]).strip() or active_spec or ""
        return spec_status(cwd, name) if name else SpecCommandResult("Usage: /spec status <name>")
    if command == "approve":
        name = tokens[1] if len(tokens) > 1 else (active_spec or "")
        stage = tokens[2].lower() if len(tokens) > 2 else ""
        return _approve(cwd, name, stage)
    if command == "implement":
        name = tokens[1] if len(tokens) > 1 else (active_spec or "")
        spec = _resolve(cwd, name)
        if spec is None:
            return SpecCommandResult(f"Spec '{name}' was not found.")
        tasks_file = _tasks_filename(spec)
        if _status(spec / tasks_file) != "approved":
            return SpecCommandResult("Approve the task list before implementation.", active_spec=spec.name)
        seed = (
            f"Implement the approved spec in `.jettstui/specs/{spec.name}/`. "
            f"Read requirements.md, design.md, and {tasks_file} first. Execute tasks "
            f"in order, verify each one, and update {tasks_file} checkboxes only after "
            "the corresponding verification passes. Preserve unrelated user changes."
        )
        return SpecCommandResult(
            f"Implementation queued for '{spec.name}' in Accept Edits mode.",
            agent_seed=seed, active_spec=spec.name, requested_mode="accept-edits",
        )
    return SpecCommandResult(
        "Usage: /spec [list|new <feature>|quick <feature>|status <name>|approve <name> <requirements|design|tasks>|implement <name>]"
    )
