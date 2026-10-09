#!/usr/bin/env python3
"""Deterministic quality gate for autonomous skill changes.

The background reviewer proposes changes, but it must not grade its own work.
This module is deliberately model-free and is not exposed as a model tool.  It
checks stable, auditable properties of SKILL.md candidates and writes a small
JSONL ledger without storing the skill contents themselves.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

import yaml

from jettstui_constants import get_jettstui_home


_TRIGGER_RE = re.compile(r"\b(use|activate|run|apply)\s+(this\s+)?(skill\s+)?when\b|\bwhen\s+to\s+use\b", re.I)
_STEP_RE = re.compile(r"(?m)^\s*(?:\d+[.)]|[-*]\s+\[[ xX]\])\s+")
_VERIFY_RE = re.compile(r"\b(verify|verification|validate|test|check|expected|success criteria)\b", re.I)
_PITFALL_RE = re.compile(r"\b(pitfall|failure|fails?|error|gotcha|troubleshoot|avoid|do not|never)\b", re.I)
_BOUNDARY_RE = re.compile(r"\b(do not use|not for|out of scope|only when|require|required)\b", re.I)
_CONCRETE_RE = re.compile(r"`[^`\n]+`|(?:^|\s)(?:\.?\.?[/\\])[\w.\-/\\]+", re.M)
# The repo skill standard keeps descriptions to one short capability sentence
# and puts the trigger in a "## When to Use" section — count that as a trigger.
_WHEN_HEADING_RE = re.compile(r"(?mi)^#{1,6}\s*when\s+to\s+use\b")

# Near-duplicate guard. Token-set Jaccard over name + description. Calibrated
# on the bundled + optional library (182 skills): the most similar legitimate
# pair (claude-code vs codex) scores 0.56, so 0.6 blocks paraphrased copies
# without flagging genuinely distinct sibling skills.
DUPLICATE_SIMILARITY = 0.6
_STOPWORDS = frozenset(
    "the and for with use when this that you your from into are not any can "
    "will its via all one each using used".split()
)


def _terms(text: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-z0-9]+", text.lower())
        if len(word) > 2 and word not in _STOPWORDS
    }


def find_near_duplicate(
    name: str, description: str, existing: Iterable[Mapping[str, Any]]
) -> Optional[str]:
    """Return the name of an existing skill this candidate nearly duplicates."""
    candidate = _terms(f"{name.replace('-', ' ')} {description}")
    if not candidate:
        return None
    best_name, best_score = None, 0.0
    for other in existing:
        other_name = str(other.get("name") or "").strip()
        if not other_name or other_name == name:
            continue
        other_terms = _terms(f"{other_name.replace('-', ' ')} {other.get('description') or ''}")
        if not other_terms:
            continue
        score = len(candidate & other_terms) / len(candidate | other_terms)
        if score > best_score:
            best_name, best_score = other_name, score
    return best_name if best_score >= DUPLICATE_SIMILARITY else None


def enabled() -> bool:
    """Return whether the autonomous improvement gate is enabled."""
    try:
        from jettstui.config import cfg_get, load_config
        raw = cfg_get(load_config(), "skills", "improvement_gate", default=False)
    except Exception:
        return False
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _split(content: str) -> tuple[Optional[Dict[str, Any]], str, list[str]]:
    failures: list[str] = []
    # Windows editors and models can emit a BOM and CRLF line endings.
    content = content.lstrip("﻿").replace("\r\n", "\n")
    if not content.startswith("---\n"):
        return None, "", ["missing YAML frontmatter"]
    match = re.search(r"\n---\s*\n", content[4:])
    if not match:
        return None, "", ["unterminated YAML frontmatter"]
    end = match.end() + 4
    try:
        parsed = yaml.safe_load(content[4 : match.start() + 4]) or {}
    except Exception:
        return None, "", ["invalid YAML frontmatter"]
    if not isinstance(parsed, dict):
        return None, "", ["frontmatter must be a mapping"]
    body = content[end:].strip()
    if not str(parsed.get("name", "")).strip():
        failures.append("frontmatter has no name")
    if not str(parsed.get("description", "")).strip():
        failures.append("frontmatter has no description")
    if len(body) < 80:
        failures.append("instruction body is too short")
    return parsed, body, failures


def score_skill(content: str) -> Dict[str, Any]:
    """Score stable instructional properties, never subjective prose quality."""
    frontmatter, body, failures = _split(content)
    if frontmatter is None:
        return {"score": 0, "max_score": 8, "signals": [], "failures": failures}

    description = str(frontmatter.get("description", ""))
    text = f"{description}\n{body}"
    signals: list[str] = []

    def add(condition: bool, label: str) -> None:
        if condition:
            signals.append(label)

    add(bool(description.strip()), "description")
    add(
        bool(_TRIGGER_RE.search(description) or _WHEN_HEADING_RE.search(body)),
        "explicit trigger",
    )
    add(bool(_BOUNDARY_RE.search(text)), "scope boundary")
    add(bool(_STEP_RE.search(body)), "ordered/checklist procedure")
    add(bool(_CONCRETE_RE.search(body)), "concrete command or path")
    add(bool(_VERIFY_RE.search(body)), "verification")
    add(bool(_PITFALL_RE.search(body)), "failure guidance")
    add(80 <= len(body) <= 24000, "bounded instruction size")
    return {
        "score": len(signals),
        "max_score": 8,
        "signals": signals,
        "failures": failures,
    }


def evaluate_candidate(
    *,
    action: str,
    name: str,
    candidate: str,
    before: str = "",
    existing: Optional[Iterable[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Evaluate a proposed SKILL.md create/edit/patch.

    Creates need a usable baseline score and must not near-duplicate an
    existing skill (``existing``: ``{"name", "description"}`` mappings) — the
    library grows by improving umbrella skills, and every extra skill costs an
    index line on every request. Existing skills may receive narrow
    corrections that keep the same score, but autonomous changes cannot remove
    two or more independent quality signals.
    """
    after_eval = score_skill(candidate)
    before_eval = score_skill(before) if before else None
    # An edit is judged on what it changes: structural failures the skill
    # already had (e.g. an already-short body) don't block a focused fix.
    inherited = set(before_eval["failures"]) if before_eval is not None else set()
    reasons = [f for f in after_eval["failures"] if f not in inherited]
    verdict = "pass"
    duplicate_of = None
    if action == "create" and existing is not None and not reasons:
        frontmatter, _body, _failures = _split(candidate)
        duplicate_of = find_near_duplicate(
            str((frontmatter or {}).get("name") or name),
            str((frontmatter or {}).get("description") or ""),
            existing,
        )

    if reasons:
        verdict = "block"
    elif duplicate_of:
        verdict = "block"
        reasons.append(
            f"near-duplicate of existing skill '{duplicate_of}'; patch that "
            "skill instead of creating a new one"
        )
    elif action == "create" and after_eval["score"] < 5:
        verdict = "block"
        reasons.append("new autonomous skills require at least 5/8 quality signals")
    elif before_eval is not None and after_eval["score"] <= before_eval["score"] - 2:
        verdict = "block"
        reasons.append("candidate removes two or more instructional quality signals")

    before_score = before_eval["score"] if before_eval is not None else None
    delta = after_eval["score"] - before_score if before_score is not None else None
    if not reasons:
        reasons.append("fixed structural checks passed; human approval is still required")
    return {
        "version": 1,
        "verdict": verdict,
        "action": action,
        "skill": name,
        "before_score": before_score,
        "after_score": after_eval["score"],
        "max_score": after_eval["max_score"],
        "delta": delta,
        "signals": after_eval["signals"],
        "duplicate_of": duplicate_of,
        "reasons": reasons,
        "candidate_sha256": hashlib.sha256(candidate.encode("utf-8")).hexdigest()[:16],
    }


def record_evaluation(evaluation: Dict[str, Any]) -> None:
    """Append a content-free audit event. Failure never permits a blocked write."""
    event = {"timestamp": time.time(), **evaluation}
    path = Path(get_jettstui_home()) / "logs" / "self_improvement.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
