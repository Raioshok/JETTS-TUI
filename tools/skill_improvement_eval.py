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
from typing import Any, Dict, Optional

import yaml

from freeide_constants import get_freeide_home


_TRIGGER_RE = re.compile(r"\b(use|activate|run|apply)\s+(this\s+)?(skill\s+)?when\b|\bwhen\s+to\s+use\b", re.I)
_STEP_RE = re.compile(r"(?m)^\s*(?:\d+[.)]|[-*]\s+\[[ xX]\])\s+")
_VERIFY_RE = re.compile(r"\b(verify|verification|validate|test|check|expected|success criteria)\b", re.I)
_PITFALL_RE = re.compile(r"\b(pitfall|failure|fails?|error|gotcha|troubleshoot|avoid|do not|never)\b", re.I)
_BOUNDARY_RE = re.compile(r"\b(do not use|not for|out of scope|only when|require|required)\b", re.I)
_CONCRETE_RE = re.compile(r"`[^`\n]+`|(?:^|\s)(?:\.?\.?[/\\])[\w.\-/\\]+", re.M)


def enabled() -> bool:
    """Return whether the autonomous improvement gate is enabled."""
    try:
        from freeide_cli.config import cfg_get, load_config
        raw = cfg_get(load_config(), "skills", "improvement_gate", default=False)
    except Exception:
        return False
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _split(content: str) -> tuple[Optional[Dict[str, Any]], str, list[str]]:
    failures: list[str] = []
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
    add(bool(_TRIGGER_RE.search(description)), "explicit trigger")
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
    *, action: str, name: str, candidate: str, before: str = ""
) -> Dict[str, Any]:
    """Evaluate a proposed SKILL.md create/edit/patch.

    Creates need a usable baseline score. Existing skills may receive narrow
    corrections that keep the same score, but autonomous changes cannot remove
    two or more independent quality signals.
    """
    after_eval = score_skill(candidate)
    before_eval = score_skill(before) if before else None
    reasons = list(after_eval["failures"])
    verdict = "pass"

    if reasons:
        verdict = "block"
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
        "reasons": reasons,
        "candidate_sha256": hashlib.sha256(candidate.encode("utf-8")).hexdigest()[:16],
    }


def record_evaluation(evaluation: Dict[str, Any]) -> None:
    """Append a content-free audit event. Failure never permits a blocked write."""
    event = {"timestamp": time.time(), **evaluation}
    path = Path(get_freeide_home()) / "logs" / "self_improvement.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
