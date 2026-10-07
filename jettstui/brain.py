"""Obsidian-backed project brain scaffolding and maintenance prompts.

The deterministic setup stays deliberately boring: plain Markdown, native
Obsidian properties/Bases, and no mandatory community plugins. LLM work is
queued as a normal agent turn by ``/brain sync|improve`` so this feature adds
no model-tool schema and does not disturb prompt caching.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
MANIFEST_NAME = ".jettstui-brain.json"

FOLDERS = (
    ".obsidian",
    "00-System",
    "01-Projects",
    "02-Knowledge",
    "03-Skills",
    "04-Architecture",
    "05-Summaries",
    "06-Agents",
    "07-ContextCache/Session",
    "07-ContextCache/Project",
    "07-ContextCache/Vault",
    "07-ContextCache/Global",
    "08-Decisions",
    "09-Research",
    "10-Workflows",
    "11-Inbox",
    "12-Daily",
    "Templates",
    "Archive",
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return cleaned[:80] or "project"


def resolve_vault_path(explicit: str | os.PathLike[str] | None = None) -> Path:
    """Resolve explicit path > config.yaml > legacy env > friendly default."""
    if explicit:
        return Path(explicit).expanduser().resolve()
    try:
        from jettstui.config import load_config

        obsidian = (load_config().get("obsidian") or {})
        configured = str(obsidian.get("vault_path") or "").strip()
        if configured:
            return Path(configured).expanduser().resolve()
    except Exception:
        pass
    legacy = os.environ.get("OBSIDIAN_VAULT_PATH", "").strip()
    if legacy:
        return Path(legacy).expanduser().resolve()
    return (Path.home() / "Documents" / "JettsTUI Brain").resolve()


def _frontmatter(
    note_type: str,
    *,
    status: str = "active",
    importance: int = 3,
    template_date: bool = False,
) -> str:
    updated = "{{date:YYYY-MM-DD}}" if template_date else ""
    return (
        "---\n"
        f"type: {note_type}\n"
        f"status: {status}\n"
        f"importance: {importance}\n"
        f'updated: "{updated}"\n'
        "source_hash: \"\"\n"
        "confidence: verified\n"
        "tags: []\n"
        "---\n"
    )


def _base_files(project_path: Path | None) -> dict[str, str]:
    project_name = project_path.name if project_path else "Example Project"
    project_slug = _slug(project_name)
    project_abs = str(project_path.resolve()) if project_path else ""
    source_prompt = (
        "# Token Optimization Mastermind — operating brief\n\n"
        "Build a persistent, local-first knowledge system for coding agents. "
        "Minimize repeated context without hiding uncertainty or replacing source-of-truth files.\n\n"
        "## Contract\n\n"
        "1. Retrieve progressively: index → 50-token summary → 100-token summary → "
        "250-token summary → raw source only when needed.\n"
        "2. Re-read raw source whenever its content hash changed; never trust a stale summary.\n"
        "3. Search narrowly by project, type, tags, and links before semantic search.\n"
        "4. Record provenance, confidence, observed-at time, and contradictions.\n"
        "5. Treat decisions, tasks, preferences, and factual knowledge as different note types.\n"
        "6. Never claim token savings without a measured baseline and actual counters.\n"
        "7. Preserve human edits. Archive superseded notes; do not silently destroy history.\n"
        "8. Prefer native Markdown, properties, links, Bases, and the official Obsidian CLI.\n"
    )
    dashboard = (
        "# Brain Dashboard\n\n"
        "> [!tip] Start here\n"
        "> Capture first, organize later: [[11-Inbox/Inbox|Inbox]]. "
        "Run `jettstui brain status` for measured health.\n\n"
        "## Focus\n\n"
        "- [[01-Projects/Project Index|Projects]]\n"
        "- [[08-Decisions/Decision Log|Decisions]]\n"
        "- [[10-Workflows/Review Workflow|Review workflow]]\n"
        "- [[00-System/Metrics|Measured token metrics]]\n\n"
        "## Live knowledge views\n\n"
        "![[00-System/Brain.base]]\n\n"
        "## Quick commands\n\n"
        "```text\n"
        "jettstui brain capture \"an idea, task, or fact\"\n"
        "jettstui                       # then /brain sync\n"
        "jettstui brain doctor\n"
        "obsidian open path=Dashboard.md\n"
        "```\n"
    )
    base = """filters:
  and:
    - file.ext == "md"
    - file.folder != "Templates"
views:
  - type: table
    name: Active knowledge
    filters:
      and:
        - status != "archived"
    order:
      - file.name
      - type
      - status
      - importance
      - updated
  - type: table
    name: Decisions
    filters:
      and:
        - type == "decision"
    order:
      - file.name
      - status
      - updated
  - type: table
    name: Open work
    filters:
      or:
        - type == "task"
        - status == "needs-review"
    order:
      - file.name
      - type
      - status
      - importance
"""
    files = {
        ".obsidian/app.json": "{}\n",
        "Dashboard.md": dashboard,
        "00-System/Brain Prompt.md": source_prompt,
        "00-System/Agent Protocol.md": """# Agent Protocol

## Start of work

1. Read [[01-Projects/Project Index]] and the selected project's `project-index.md`.
2. Read the relevant skill and architecture map.
3. Follow links or search within the selected project/type. Do not scan the vault.
4. Load the smallest summary tier that answers the question.
5. Read raw source only to implement, verify, or refresh a changed summary.

## End of work

1. Update changed-file summaries and their `source_hash`.
2. Record durable decisions in [[08-Decisions/Decision Log]].
3. Move actionable inbox items into project/task notes.
4. Mark contradictions `status: needs-review`; keep both claims and cite evidence.
5. Update [[00-System/Metrics]] with measured counts only.

## Memory quality

- Facts need source and observation date.
- Preferences need an owner and scope.
- Decisions need context, options, outcome, and consequences.
- Summaries expire when their source hash changes.
- Similarity is a retrieval hint, never proof that two facts are equivalent.
""",
        "00-System/Schema.md": """# Note Schema

Every durable note uses properties where they make sense:

| Property | Meaning |
| --- | --- |
| `type` | project, summary, decision, task, skill, research, person, system |
| `status` | active, needs-review, superseded, archived |
| `importance` | 1–5 retrieval priority; not truth confidence |
| `updated` | last meaningful review date |
| `source_hash` | SHA-256 of source content for invalidation |
| `confidence` | verified, reported, inferred, disputed |
| `tags` | small controlled vocabulary |

Relationships use links plus optional typed frontmatter such as `depends_on`,
`implements`, `supersedes`, `contradicts`, and `owned_by`. Keep relationships
human-readable; avoid duplicating the same graph in an opaque database.
""",
        "00-System/Metrics.md": """# Measured Token Metrics

> [!warning] No invented savings
> Establish a baseline before reporting percentages. Targets are aspirations, not results.

| Metric | Baseline | Current | Method |
| --- | ---: | ---: | --- |
| Input tokens per comparable task | — | — | Provider usage logs |
| Context cache hit ratio | — | — | Cache hits / eligible lookups |
| Files avoided | — | — | Candidate files - raw files opened |
| Summary compression ratio | — | — | Raw tokens / summary tokens |
| Stale summaries | — | 0 | Hash mismatch count |
| Unresolved contradictions | — | 0 | `status: needs-review` notes |
| Retrieval latency p50/p95 | — | — | Timed retrieval operations |

Review weekly. Segment by project and task class so easy tasks do not inflate savings.
""",
        "00-System/Brain.base": base,
        "01-Projects/Project Index.md": f"""# Project Index

## Active

- [[01-Projects/{project_slug}/project-index|{project_name}]]

## Paused

## Archived
""",
        "02-Knowledge/Knowledge Index.md": "# Knowledge Index\n\nDurable concepts and facts, linked to sources and projects.\n",
        "03-Skills/Skill Index.md": """# Skill Index

Store stable working preferences and reusable procedures here. Keep session-specific
evidence in linked notes, and keep executable JettsTUI skills in JettsTUI's skill store.

- [[03-Skills/coding]]
- [[03-Skills/backend]]
- [[03-Skills/frontend]]
- [[03-Skills/database]]
- [[03-Skills/security]]
- [[03-Skills/devops]]
- [[03-Skills/saas]]
- [[03-Skills/deployment]]
- [[03-Skills/pricing]]
""",
        "04-Architecture/Architecture Index.md": "# Architecture Index\n\nCross-project maps and reusable architectural patterns.\n",
        "05-Summaries/Summary Index.md": """# Summary Index

Summaries are derivatives, not sources of truth. Each summary must carry the current
source hash and link to its source. Generate 50/100/250-token tiers only where repeated
retrieval justifies their maintenance cost.
""",
        "06-Agents/Agent Context.md": """# Agent Context

## Current priorities

## Working agreements

- Use [[00-System/Agent Protocol]].
- Surface uncertainty and contradictions.
- Leave a concise handoff after material work.

## Handoff

No active handoff.
""",
        "07-ContextCache/README.md": """# Context Cache

- `Session/`: disposable pointers for one conversation.
- `Project/`: project indexes and frequently reused task context.
- `Vault/`: stable cross-project knowledge.
- `Global/`: durable user preferences and universal procedures.

Cache entries need source links, hashes, creation time, last-hit time, and a reason to exist.
Invalidate on source-hash mismatch. Promotion requires repeated verified use; demote stale entries.
""",
        f"07-ContextCache/Project/{project_slug}-source-manifest.json": json.dumps(
            {
                "schema_version": 1,
                "project": project_abs,
                "generated_at": None,
                "files": {},
            },
            indent=2,
            sort_keys=True,
        ) + "\n",
        "08-Decisions/Decision Log.md": """# Decision Log

Record decisions as individual notes from [[Templates/Decision]]. Link them here after review.

## Active

## Superseded
""",
        "09-Research/Research Index.md": "# Research Index\n\nResearch notes require source URLs, access dates, and confidence.\n",
        "10-Workflows/Token Optimization Workflow.md": """# Token Optimization Workflow

```mermaid
flowchart LR
  Q[Task] --> I[Project index]
  I --> G[Dependency / decision maps]
  G --> S{Smallest useful summary}
  S -->|enough| A[Act]
  S -->|insufficient| R[Targeted raw files]
  R --> U[Refresh changed summaries]
  A --> M[Record measured retrieval metrics]
  U --> M
```

Use lexical and property filters first. Add embeddings only when measured misses justify
them, then use hybrid retrieval and reranking. Fetch graph neighbours after the initial
hit; cap breadth and total context. Stable prompt prefixes stay byte-identical.
""",
        "10-Workflows/Review Workflow.md": """# Review Workflow

## Daily, lightweight

1. Triage [[11-Inbox/Inbox]].
2. Convert action items to tasks and link their project.
3. Refresh summaries only for changed source hashes.

## Weekly, conflict-aware

1. Run `jettstui brain doctor`.
2. Review orphaned, stale, disputed, and `needs-review` notes.
3. Consolidate duplicates while preserving redirects and provenance.
4. Promote frequently reused context; archive low-value cache entries.
5. Compare token/latency metrics against a task-matched baseline.

Do not run an LLM on an unchanged vault merely because a timer fired. Gate scheduled
review on inbox content, source changes, unresolved conflicts, or stale summaries.
""",
        "11-Inbox/Inbox.md": """# Inbox

Fast capture lives here. Add first; classify during review.

## Unprocessed
""",
        "12-Daily/README.md": "# Daily Notes\n\nUse [[Templates/Daily]] for brief logs, decisions, and follow-ups.\n",
        "Templates/Daily.md": _frontmatter("daily", template_date=True) + "\n# {{date:YYYY-MM-DD}}\n\n## Focus\n\n## Notes\n\n## Decisions\n\n## Tasks\n\n- [ ] \n",
        "Templates/Decision.md": _frontmatter("decision", importance=4, template_date=True) + "\n# {{title}}\n\n## Context\n\n## Options\n\n## Decision\n\n## Consequences\n\n## Evidence\n",
        "Templates/File Summary.md": _frontmatter("summary", template_date=True) + "\n# {{title}}\n\n- Source: [[]]\n- Source hash: `replace-me`\n- Importance: 1–5\n\n## 50 tokens\n\n## 100 tokens\n\n## 250 tokens\n\n## Imports / exports\n\n## Business rules\n\n## Related files\n",
        "Templates/Project.md": _frontmatter("project", importance=4, template_date=True) + "\n# {{title}}\n\n## Outcome\n\n## Current state\n\n## Architecture\n\n## Tasks\n\n## Decisions\n",
        "Templates/Skill.md": _frontmatter("skill", importance=4, template_date=True) + "\n# {{title}}\n\n## When to use\n\n## Procedure\n\n## Preferences\n\n## Pitfalls\n\n## Evidence\n",
        "Archive/README.md": "# Archive\n\nSuperseded material with preserved provenance and inbound links.\n",
        f"01-Projects/{project_slug}/project-index.md": f"""{_frontmatter('project', importance=5)}
# {project_name}

- Repository: `{project_abs or 'set during /brain sync'}`
- [[01-Projects/{project_slug}/architecture-map|Architecture map]]
- [[01-Projects/{project_slug}/feature-map|Feature map]]
- [[01-Projects/{project_slug}/dependency-map|Dependency map]]
- [[01-Projects/{project_slug}/entity-map|Entity map]]
- [[01-Projects/{project_slug}/api-map|API map]]

## Objective

## Current state

## Retrieval entry points

## Open tasks
""",
    }
    for name in ("architecture-map", "feature-map", "dependency-map", "entity-map", "api-map"):
        title = name.replace("-", " ").title()
        files[f"01-Projects/{project_slug}/{name}.md"] = (
            _frontmatter("architecture", importance=4)
            + f"\n# {title}\n\nGenerated incrementally by `/brain sync`.\n"
        )
    for name in ("coding", "backend", "frontend", "database", "security", "devops", "saas", "deployment", "pricing"):
        files[f"03-Skills/{name}.md"] = _frontmatter("skill", importance=4) + f"\n# {name.title()}\n\n## Preferences\n\n## Reusable procedures\n\n## Pitfalls\n"
    return files


@dataclass
class SetupResult:
    vault: Path
    created: list[str]
    updated: list[str]
    preserved: list[str]


def _read_manifest(vault: Path) -> dict[str, Any]:
    path = vault / MANIFEST_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _write_config(vault: Path) -> None:
    from jettstui.config import atomic_config_write, get_config_path, read_raw_config

    config = read_raw_config()
    obsidian = config.setdefault("obsidian", {})
    if not isinstance(obsidian, dict):
        obsidian = {}
        config["obsidian"] = obsidian
    obsidian["vault_path"] = str(vault)
    brain = obsidian.setdefault("brain", {})
    if not isinstance(brain, dict):
        brain = {}
        obsidian["brain"] = brain
    brain["enabled"] = True
    atomic_config_write(get_config_path(), config, sort_keys=False)


def setup_brain(vault_path: str | os.PathLike[str] | None = None, *, project_path: str | os.PathLike[str] | None = None) -> SetupResult:
    vault = resolve_vault_path(vault_path)
    if vault.exists() and not vault.is_dir():
        raise ValueError(f"Vault path is a file: {vault}")
    vault.mkdir(parents=True, exist_ok=True)
    project = Path(project_path).expanduser().resolve() if project_path else Path.cwd().resolve()
    previous = _read_manifest(vault)
    managed = previous.get("managed") if isinstance(previous.get("managed"), dict) else {}
    desired = _base_files(project)
    created: list[str] = []
    updated: list[str] = []
    preserved: list[str] = []
    next_managed: dict[str, str] = {}
    for folder in FOLDERS:
        (vault / folder).mkdir(parents=True, exist_ok=True)
    for rel, content in desired.items():
        path = vault / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        new_hash = _sha256(content)
        if not path.exists():
            path.write_text(content, encoding="utf-8")
            created.append(rel)
            next_managed[rel] = new_hash
            continue
        current = path.read_text(encoding="utf-8", errors="replace")
        current_hash = _sha256(current)
        old_template_hash = managed.get(rel)
        if current_hash == new_hash:
            next_managed[rel] = new_hash
        elif old_template_hash and current_hash == old_template_hash:
            path.write_text(content, encoding="utf-8")
            updated.append(rel)
            next_managed[rel] = new_hash
        else:
            preserved.append(rel)
            if old_template_hash:
                next_managed[rel] = old_template_hash
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "vault": str(vault),
        "project": str(project),
        "managed": next_managed,
    }
    (vault / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_config(vault)
    return SetupResult(vault, created, updated, preserved)


def capture(text: str, vault_path: str | os.PathLike[str] | None = None) -> Path:
    text = text.strip()
    if not text:
        raise ValueError("Capture text cannot be empty")
    vault = resolve_vault_path(vault_path)
    inbox = vault / "11-Inbox" / "Inbox.md"
    if not inbox.exists():
        setup_brain(vault)
    with inbox.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"\n- {_now()} — {text}\n")
    return inbox


def brain_status(vault_path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    vault = resolve_vault_path(vault_path)
    markdown = list(vault.rglob("*.md")) if vault.is_dir() else []
    inbox = vault / "11-Inbox" / "Inbox.md"
    inbox_items = 0
    if inbox.exists():
        inbox_items = sum(1 for line in inbox.read_text(encoding="utf-8", errors="replace").splitlines() if line.startswith("- "))
    manifest = _read_manifest(vault)
    return {
        "vault": str(vault),
        "initialized": bool(manifest.get("schema_version")),
        "schema_version": manifest.get("schema_version"),
        "notes": len(markdown),
        "inbox_items": inbox_items,
        "obsidian_cli": shutil.which("obsidian") is not None,
        "dashboard": (vault / "Dashboard.md").exists(),
    }


_WIKILINK_RE = re.compile(r"(?<!!)\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")


def brain_doctor(vault_path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    vault = resolve_vault_path(vault_path)
    missing = [folder for folder in FOLDERS if not (vault / folder).is_dir()]
    notes = list(vault.rglob("*.md")) if vault.is_dir() else []
    names = {path.stem.casefold() for path in notes}
    relative_no_ext = {path.relative_to(vault).with_suffix("").as_posix().casefold() for path in notes}
    unresolved: set[str] = set()
    for path in notes:
        content = path.read_text(encoding="utf-8", errors="replace")
        for target in _WIKILINK_RE.findall(content):
            normalized = target.strip().replace("\\", "/").removesuffix(".md").casefold()
            if normalized not in relative_no_ext and Path(normalized).name not in names:
                unresolved.add(target.strip())
    return {
        "vault": str(vault),
        "missing_folders": missing,
        "unresolved_links": sorted(unresolved),
        "ok": not missing and not unresolved,
    }


def build_maintenance_prompt(action: str, vault_path: str | os.PathLike[str] | None = None, *, project_path: str | os.PathLike[str] | None = None) -> str:
    vault = resolve_vault_path(vault_path)
    project = Path(project_path).expanduser().resolve() if project_path else Path.cwd().resolve()
    common = f"""Maintain the Obsidian brain at this exact path: {vault}
Current project: {project}

Read 00-System/Agent Protocol.md and the relevant project index first. Use the
bundled obsidian skill for file operations. Preserve human edits. Never scan the
whole vault during normal retrieval. Record provenance and uncertainty. Do not
invent token-savings numbers. Finish with a compact report of files changed,
items needing human review, and measured metrics available.
"""
    if action == "sync":
        return common + """
Synchronize this project incrementally:
1. Build or update a source manifest containing path, size, mtime, and SHA-256.
2. Compare it with the prior manifest and inspect only added, changed, moved, or
   deleted files. Honor .gitignore and exclude dependencies/build artifacts.
3. Update project-index, architecture, feature, dependency, entity, and API maps.
4. Create 50/100/250-token summaries only for important, repeatedly useful files.
5. Mark summaries stale when their source hash differs; refresh only those needed.
6. Link decisions, tasks, skills, and research instead of duplicating their text.
"""
    return common + """
Run a conflict-aware improvement review:
1. Triage unprocessed inbox entries into projects, tasks, decisions, or knowledge.
2. Find stale summaries via source hashes, unresolved `needs-review` notes, and
   conflicting claims among directly related notes. Do not perform a broad
   semantic rewrite of unchanged content.
3. Consolidate obvious duplicates while leaving redirects and provenance.
4. Extract actionable tasks and connect them to their project and evidence.
5. Promote context only after repeated verified use; archive stale cache entries.
6. Update the dashboard and measured metrics. If there is no material change,
   make no edits and report that the gate correctly skipped improvement work.
"""


def open_dashboard(vault_path: str | os.PathLike[str] | None = None) -> None:
    vault = resolve_vault_path(vault_path)
    executable = shutil.which("obsidian")
    if not executable:
        raise RuntimeError("Obsidian CLI not found. Enable it in Obsidian Settings → General.")
    subprocess.run([executable, "open", "path=Dashboard.md"], cwd=vault, check=True)


@dataclass
class BrainSlashResult:
    text: str
    prompt: str | None = None


def handle_brain_slash(command: str, *, cwd: str | os.PathLike[str] | None = None) -> BrainSlashResult:
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        return BrainSlashResult(f"Invalid /brain command: {exc}")
    args = tokens[1:] if tokens and tokens[0].lstrip("/").lower() == "brain" else tokens
    action = args[0].lower() if args else "status"
    rest = args[1:]
    project = Path(cwd).resolve() if cwd else Path.cwd().resolve()
    if action == "init":
        result = setup_brain(rest[0] if rest else None, project_path=project)
        return BrainSlashResult(
            f"Brain ready at {result.vault}\n"
            f"Created {len(result.created)}, updated {len(result.updated)}, "
            f"preserved {len(result.preserved)} customized files."
        )
    if action == "capture":
        if not rest:
            return BrainSlashResult("Usage: /brain capture <idea, task, or fact>")
        path = capture(" ".join(rest))
        return BrainSlashResult(f"Captured in {path}")
    if action in {"sync", "improve"}:
        if not brain_status()["initialized"]:
            setup_brain(project_path=project)
        return BrainSlashResult(
            f"Queued incremental brain {action} for {project}.",
            build_maintenance_prompt(action, project_path=project),
        )
    if action == "doctor":
        report = brain_doctor()
        return BrainSlashResult(_format_doctor(report))
    if action == "open":
        try:
            open_dashboard()
            return BrainSlashResult("Opened Brain Dashboard in Obsidian.")
        except Exception as exc:
            return BrainSlashResult(f"Could not open Obsidian: {exc}")
    if action == "status":
        return BrainSlashResult(_format_status(brain_status()))
    return BrainSlashResult("Usage: /brain [init [vault]|status|capture <text>|sync|improve|doctor|open]")


def _format_status(status: dict[str, Any]) -> str:
    cli = "available" if status["obsidian_cli"] else "not registered"
    return (
        f"Brain: {status['vault']}\n"
        f"  initialized: {'yes' if status['initialized'] else 'no'}\n"
        f"  notes: {status['notes']} · inbox: {status['inbox_items']}\n"
        f"  Obsidian CLI: {cli}"
    )


def _format_doctor(report: dict[str, Any]) -> str:
    lines = [f"Brain doctor: {report['vault']}"]
    lines.append(f"  folders: {'ok' if not report['missing_folders'] else 'missing ' + ', '.join(report['missing_folders'])}")
    if report["unresolved_links"]:
        preview = ", ".join(report["unresolved_links"][:10])
        more = len(report["unresolved_links"]) - 10
        lines.append(f"  unresolved links: {preview}" + (f" (+{more} more)" if more else ""))
    else:
        lines.append("  unresolved links: none")
    return "\n".join(lines)


def brain_command(args: Any) -> int:
    action = getattr(args, "brain_action", None) or "status"
    vault = getattr(args, "vault", None)
    try:
        if action == "init":
            result = setup_brain(vault, project_path=getattr(args, "project", None))
            print(f"✓ Brain ready: {result.vault}")
            print(f"  created {len(result.created)} · updated {len(result.updated)} · preserved {len(result.preserved)}")
            print("  Next: start `jettstui`, then run /brain sync")
        elif action == "capture":
            text = " ".join(args.text) if isinstance(args.text, list) else args.text
            print(f"✓ Captured in {capture(text, vault)}")
        elif action == "doctor":
            report = brain_doctor(vault)
            print(_format_doctor(report))
            return 0 if report["ok"] else 1
        elif action == "prompt":
            print(build_maintenance_prompt(args.mode, vault, project_path=getattr(args, "project", None)))
        elif action == "open":
            open_dashboard(vault)
            print("✓ Opened Brain Dashboard in Obsidian")
        else:
            print(_format_status(brain_status(vault)))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"brain: {exc}")
        return 1
