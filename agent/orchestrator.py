"""Multi-model orchestrator flow: plan -> execute -> review + verify.

Each stage runs as an isolated subagent on its own model, so a user can have
one model plan, another do the work, and independent models review the result
and check security & quality.  Review findings loop back to the executor for a
bounded number of rounds.

Config (``orchestrator:`` in config.yaml)::

    orchestrator:
      enabled: false
      max_review_rounds: 2
      roles:
        planner:  {provider: "", model: ""}   # empty model = Auto
        executor: {provider: "", model: ""}
        reviewer: {provider: "", model: ""}
        verifier: {provider: "", model: ""}

Auto picks a model per role from the user's configured providers, using
models.dev metadata (reasoning, tool calling, price tier, recency) with a
name-based fallback, and prefers a different model family for review than the
one that wrote the code so the review is genuinely independent.

The flow is exposed to the agent as the config-gated ``orchestrate`` tool
(``tools/orchestrator_tool.py``) and to the desktop app via the
``orchestrator.get`` / ``orchestrator.save`` RPCs.
"""

from __future__ import annotations

import contextvars
import logging
import math
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


# ─── Roles ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RoleSpec:
    id: str
    title: str
    brief: str
    # Review roles must end with a VERDICT line the runner parses.
    gives_verdict: bool = False


_VERDICT_RULE = (
    "Do not modify any files. End your answer with exactly one line:\n"
    "VERDICT: APPROVED\n"
    "or\n"
    "VERDICT: CHANGES_REQUESTED\n"
    "When requesting changes, list each required fix above the verdict line "
    "as a numbered item with the file and the concrete problem. Only request "
    "changes for real defects, not style preferences."
)

ROLES: Tuple[RoleSpec, ...] = (
    RoleSpec(
        "planner",
        "Planner",
        "You are the PLANNER in a multi-agent flow. Investigate the codebase "
        "and environment as needed, then write a concrete, numbered "
        "implementation plan for the task: files to change, the approach, "
        "edge cases, and how to verify the result. Do not modify any files — "
        "another agent will execute your plan.",
    ),
    RoleSpec(
        "executor",
        "Executor",
        "You are the EXECUTOR in a multi-agent flow. Carry out the task by "
        "following the plan, making the actual changes and running the "
        "relevant checks/tests. Finish with a concise summary of what you "
        "changed (files), what you verified, and anything left undone.",
    ),
    RoleSpec(
        "reviewer",
        "Reviewer",
        "You are the REVIEWER in a multi-agent flow. Independently inspect the "
        "changes the executor made (read the modified files / diff) and check "
        "them for correctness against the task and plan: bugs, missed "
        "requirements, broken edge cases. " + _VERDICT_RULE,
        gives_verdict=True,
    ),
    RoleSpec(
        "verifier",
        "Security & quality",
        "You are the SECURITY & QUALITY verifier in a multi-agent flow. Inspect "
        "the changes the executor made for security problems (injection, "
        "secrets, unsafe input handling, permissions) and quality problems "
        "(failing tests or lint, missing error handling, dead code). Run the "
        "project's tests/linters when available. " + _VERDICT_RULE,
        gives_verdict=True,
    ),
)

ROLE_IDS: Tuple[str, ...] = tuple(r.id for r in ROLES)
_ROLE_BY_ID: Dict[str, RoleSpec] = {r.id: r for r in ROLES}

DEFAULT_MAX_REVIEW_ROUNDS = 2
MAX_REVIEW_ROUNDS_CAP = 5
# Per-stage summary budget carried between stages and into the final report.
_STAGE_SUMMARY_CHARS = 8000


# ─── Config ─────────────────────────────────────────────────────────────────


def _load_raw_config() -> dict:
    try:
        from jettstui.config import load_config

        cfg = load_config()
        return cfg if isinstance(cfg, dict) else {}
    except Exception as exc:  # noqa: BLE001 — config unreadable → defaults
        logger.debug("orchestrator: config load failed: %s", exc)
        return {}


def normalize_config(raw: Any) -> dict:
    """Return a fully-populated, validated ``orchestrator`` section."""
    section = raw if isinstance(raw, dict) else {}
    try:
        rounds = int(section.get("max_review_rounds", DEFAULT_MAX_REVIEW_ROUNDS))
    except (TypeError, ValueError):
        rounds = DEFAULT_MAX_REVIEW_ROUNDS
    rounds = max(0, min(MAX_REVIEW_ROUNDS_CAP, rounds))

    raw_roles = section.get("roles") if isinstance(section.get("roles"), dict) else {}
    roles: Dict[str, Dict[str, str]] = {}
    for role_id in ROLE_IDS:
        entry = raw_roles.get(role_id) if isinstance(raw_roles.get(role_id), dict) else {}
        roles[role_id] = {
            "provider": str(entry.get("provider") or "").strip(),
            "model": str(entry.get("model") or "").strip(),
        }
    return {
        "enabled": bool(section.get("enabled", False)),
        "max_review_rounds": rounds,
        "roles": roles,
    }


def load_orchestrator_config(cfg: Optional[dict] = None) -> dict:
    cfg = _load_raw_config() if cfg is None else cfg
    return normalize_config(cfg.get("orchestrator") if isinstance(cfg, dict) else None)


def is_enabled() -> bool:
    return load_orchestrator_config()["enabled"]


# ─── Auto model selection ───────────────────────────────────────────────────


@dataclass
class Candidate:
    provider: str
    model: str
    family: str = ""
    reasoning: Optional[bool] = None
    tool_call: Optional[bool] = None
    cost_output: float = 0.0
    context_window: int = 0
    release_date: str = ""


@dataclass
class Assignment:
    role: str
    provider: str
    model: str
    auto: bool
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# Name heuristics for models missing from models.dev.
_STRONG_TOKENS = ("opus", "ultra", "-pro", "pro-", "gpt-5", "o3", "o4", "max", "large", "405b", "grok-4", "r1")
_FAST_TOKENS = ("mini", "flash", "haiku", "nano", "lite", "small", "tiny", "8b", "7b", "3b", "1b", "fast", "instant")
_CODER_TOKENS = ("coder", "codex", "code", "sonnet", "devstral")

# How much each role cares about raw strength, reasoning, coding fit and cost.
_ROLE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "planner": {"strength": 1.0, "reasoning": 1.0, "coder": 0.2, "cost": 0.1},
    "executor": {"strength": 0.8, "reasoning": 0.4, "coder": 1.0, "cost": 0.35},
    "reviewer": {"strength": 1.0, "reasoning": 0.8, "coder": 0.4, "cost": 0.1},
    "verifier": {"strength": 0.9, "reasoning": 0.8, "coder": 0.5, "cost": 0.15},
}


def _family_of(c: Candidate) -> str:
    if c.family:
        return c.family.lower()
    base = c.model.lower().rsplit("/", 1)[-1]
    return re.split(r"[-_:.]\d", base, maxsplit=1)[0] or base


def _name_strength(model: str) -> float:
    name = model.lower()
    if any(t in name for t in _FAST_TOKENS):
        return 0.3
    if any(t in name for t in _STRONG_TOKENS):
        return 0.9
    return 0.6


def _strength(c: Candidate) -> float:
    """0..1 capability estimate: price tier when known, else the model name."""
    if c.cost_output > 0:
        # $0.5/M → ~0.1, $15/M → ~0.8, $75/M → 1.0 (log scale, clamped).
        return max(0.0, min(1.0, math.log10(c.cost_output * 2 + 1) / math.log10(151)))
    return _name_strength(c.model)


def score_candidate(c: Candidate, role: str) -> float:
    w = _ROLE_WEIGHTS.get(role, _ROLE_WEIGHTS["executor"])
    strength = _strength(c)
    reasoning = 1.0 if c.reasoning else (0.5 if c.reasoning is None else 0.0)
    coder = 1.0 if any(t in c.model.lower() for t in _CODER_TOKENS) else 0.0
    cost_penalty = min(1.0, c.cost_output / 75.0) if c.cost_output > 0 else 0.0
    recency = 0.05 if c.release_date[:4] >= "2026" else 0.0
    return (
        w["strength"] * strength
        + 0.3 * w["reasoning"] * reasoning
        + 0.25 * w["coder"] * coder
        - 0.3 * w["cost"] * cost_penalty
        + recency
    )


def _usable(c: Candidate) -> bool:
    # Every stage drives tools (file reads at minimum); a model that models.dev
    # says cannot call tools would stall the flow.
    return c.tool_call is not False


def auto_assign(
    candidates: Sequence[Candidate],
    fixed: Optional[Dict[str, Tuple[str, str]]] = None,
    roles: Iterable[str] = ROLE_IDS,
) -> Dict[str, Assignment]:
    """Pick a model for each role in ``roles``.

    ``fixed`` holds roles the user pinned (role -> (provider, model)); they
    count toward family diversity so an Auto reviewer still avoids the pinned
    executor's family.
    """
    fixed = dict(fixed or {})
    pool = [c for c in candidates if _usable(c)]
    picks: Dict[str, Assignment] = {}
    if not pool:
        return picks

    families: Dict[str, str] = {}
    for role_id, (prov, model) in fixed.items():
        match = next((c for c in pool if c.provider == prov and c.model == model), None)
        families[role_id] = _family_of(match) if match else _family_of(Candidate(prov, model))

    # Executor first: review roles diversify away from whatever writes the code.
    order = sorted(roles, key=lambda r: 0 if r == "executor" else 1 if r == "planner" else 2)
    for role_id in order:
        avoid = set()
        if role_id in ("reviewer", "verifier"):
            avoid = {families[r] for r in ("executor", "reviewer") if r in families and r != role_id}
        ranked = sorted(pool, key=lambda c: score_candidate(c, role_id), reverse=True)
        best = ranked[0]
        reason = "best fit for this role among your configured models"
        if avoid:
            diverse = [c for c in ranked if _family_of(c) not in avoid]
            # Only trade down for independence when the alternative is close.
            if diverse and score_candidate(diverse[0], role_id) >= score_candidate(best, role_id) - 0.25:
                if _family_of(best) in avoid:
                    reason = "independent of the model that wrote the code"
                best = diverse[0]
        if role_id == "planner" and best.reasoning:
            reason = "strongest reasoning model available"
        elif role_id == "executor" and any(t in best.model.lower() for t in _CODER_TOKENS):
            reason = "strong coding model with tool use"
        picks[role_id] = Assignment(role_id, best.provider, best.model, True, reason)
        families[role_id] = _family_of(best)
    return picks


def _candidate_from_metadata(provider: str, model: str) -> Candidate:
    cand = Candidate(provider, model)
    try:
        from agent.models_dev import get_model_info

        info = get_model_info(provider, model)
    except Exception:  # noqa: BLE001 — metadata is a hint, never required
        info = None
    if info is not None:
        cand.family = info.family or ""
        cand.reasoning = bool(info.reasoning)
        cand.tool_call = bool(info.tool_call)
        cand.cost_output = float(info.cost_output or 0.0)
        cand.context_window = int(info.context_window or 0)
        cand.release_date = info.release_date or ""
    return cand


# Bound metadata lookups on aggregator providers that list hundreds of models.
_MAX_MODELS_PER_PROVIDER = 12


def gather_candidates() -> List[Candidate]:
    """Models from the user's authenticated providers, with metadata."""
    try:
        from jettstui.inventory import build_models_payload, load_picker_context

        payload = build_models_payload(
            load_picker_context(), explicit_only=True, picker_hints=True, featured=True
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("orchestrator: model inventory failed: %s", exc)
        return []
    rows = payload.get("providers") if isinstance(payload, dict) else None
    out: List[Candidate] = []
    seen = set()
    for row in rows or []:
        if not isinstance(row, dict) or row.get("authenticated") is False:
            continue
        slug = str(row.get("slug") or "").strip()
        models = row.get("featured_models") or row.get("models") or []
        for model in list(models)[:_MAX_MODELS_PER_PROVIDER]:
            key = (slug, str(model))
            if slug and model and key not in seen:
                seen.add(key)
                out.append(_candidate_from_metadata(slug, str(model)))
    return out


def resolve_assignments(
    config: Optional[dict] = None,
    candidates: Optional[Sequence[Candidate]] = None,
) -> Dict[str, Assignment]:
    """Resolve every role to a concrete (provider, model) or session inherit."""
    conf = config if config is not None else load_orchestrator_config()
    fixed = {
        r: (v["provider"], v["model"]) for r, v in conf["roles"].items() if v["model"]
    }
    out: Dict[str, Assignment] = {
        r: Assignment(r, prov, model, False, "chosen by you") for r, (prov, model) in fixed.items()
    }
    auto_roles = [r for r in ROLE_IDS if r not in fixed]
    if auto_roles:
        pool = gather_candidates() if candidates is None else list(candidates)
        out.update(auto_assign(pool, fixed, auto_roles))
    for role_id in ROLE_IDS:
        out.setdefault(
            role_id, Assignment(role_id, "", "", True, "no other models configured; uses the session's model")
        )
    return {r: out[r] for r in ROLE_IDS}


# ─── Flow runner ────────────────────────────────────────────────────────────


_VERDICT_RE = re.compile(r"VERDICT:\s*(APPROVED|CHANGES[_ ]REQUESTED)", re.IGNORECASE)


def parse_verdict(text: Optional[str]) -> str:
    """'approved' | 'changes_requested' | 'unknown' from a reviewer's output."""
    matches = _VERDICT_RE.findall(text or "")
    if not matches:
        return "unknown"
    return "approved" if matches[-1].upper() == "APPROVED" else "changes_requested"


def _clip(text: Optional[str], limit: int = _STAGE_SUMMARY_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n…[{len(text) - limit} chars omitted]…\n{text[-half:]}"


@dataclass
class StageResult:
    role: str
    round: int
    provider: str
    model: str
    status: str
    summary: str = ""
    error: str = ""
    verdict: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        if not d["verdict"]:
            d.pop("verdict")
        if not d["error"]:
            d.pop("error")
        return d


ChildRunner = Callable[[Any, Assignment, str], Dict[str, Any]]


def _run_child(parent_agent: Any, assignment: Assignment, goal: str) -> Dict[str, Any]:
    """Run one stage as a delegated subagent on the assignment's model."""
    from tools.delegate_tool import (
        DEFAULT_MAX_ITERATIONS,
        _build_child_preserving_parent_tools,
        _load_config as _load_delegation_config,
        _resolve_delegation_credentials,
        _run_child_lifecycle,
    )

    deleg_cfg = _load_delegation_config()
    creds = _resolve_delegation_credentials(
        {"provider": assignment.provider, "model": assignment.model}, parent_agent
    )
    try:
        max_iter = int(deleg_cfg.get("max_iterations") or DEFAULT_MAX_ITERATIONS)
    except (TypeError, ValueError):
        max_iter = DEFAULT_MAX_ITERATIONS
    child = _build_child_preserving_parent_tools(
        task_index=0,
        goal=goal,
        context=None,
        toolsets=None,
        model=creds["model"],
        max_iterations=max_iter,
        task_count=1,
        parent_agent=parent_agent,
        override_provider=creds["provider"],
        override_base_url=creds["base_url"],
        override_api_key=creds["api_key"],
        override_api_mode=creds["api_mode"],
        override_request_overrides=creds.get("request_overrides"),
        override_max_tokens=creds.get("max_output_tokens"),
        override_acp_command=creds.get("command"),
        override_acp_args=creds.get("args"),
        role="leaf",
    )
    result = _run_child_lifecycle(0, goal, child, parent_agent)
    result["model"] = getattr(child, "model", None) or assignment.model
    result["provider"] = getattr(child, "provider", None) or assignment.provider
    return result


def _stage_goal(role: RoleSpec, task: str, sections: Sequence[Tuple[str, str]]) -> str:
    parts = [f"[{role.title}] {role.brief}", f"## Task\n{task.strip()}"]
    parts.extend(f"## {title}\n{body}" for title, body in sections if body)
    return "\n\n".join(parts)


def _to_stage(role: str, rnd: int, assignment: Assignment, raw: Dict[str, Any]) -> StageResult:
    summary = _clip(raw.get("summary") if isinstance(raw, dict) else "")
    stage = StageResult(
        role=role,
        round=rnd,
        provider=str(raw.get("provider") or assignment.provider or ""),
        model=str(raw.get("model") or assignment.model or ""),
        status=str(raw.get("status") or "error"),
        summary=summary,
        error=str(raw.get("error") or ""),
    )
    if _ROLE_BY_ID[role].gives_verdict:
        stage.verdict = parse_verdict(summary) if stage.status == "completed" else "unknown"
    return stage


def _safe_run(runner: ChildRunner, parent: Any, assignment: Assignment, goal: str) -> Dict[str, Any]:
    try:
        return runner(parent, assignment, goal)
    except Exception as exc:  # noqa: BLE001 — a failed stage is reported, not raised
        logger.warning("orchestrator stage %s failed: %s", assignment.role, exc)
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}


def run_flow(
    parent_agent: Any,
    task: str,
    context: Optional[str] = None,
    *,
    config: Optional[dict] = None,
    assignments: Optional[Dict[str, Assignment]] = None,
    runner: ChildRunner = _run_child,
) -> dict:
    """Run plan -> execute -> (review || verify), looping on requested changes."""
    conf = config if config is not None else load_orchestrator_config()
    assigned = assignments if assignments is not None else resolve_assignments(conf)
    max_rounds = conf["max_review_rounds"]
    stages: List[StageResult] = []
    task_text = task.strip()
    if context and context.strip():
        task_text = f"{task_text}\n\nContext:\n{context.strip()}"

    plan = _to_stage(
        "planner", 0, assigned["planner"],
        _safe_run(runner, parent_agent, assigned["planner"], _stage_goal(_ROLE_BY_ID["planner"], task_text, ())),
    )
    stages.append(plan)
    if plan.status != "completed":
        return _report("failed", stages, assigned, "Planning stage failed.")

    feedback = ""
    rnd = 0
    verdict = "changes_requested"
    while True:
        rnd += 1
        exec_sections = [("Plan", plan.summary)]
        if feedback:
            exec_sections.append(("Review findings to fix", feedback))
        execution = _to_stage(
            "executor", rnd, assigned["executor"],
            _safe_run(runner, parent_agent, assigned["executor"],
                      _stage_goal(_ROLE_BY_ID["executor"], task_text, exec_sections)),
        )
        stages.append(execution)
        if execution.status != "completed":
            return _report("failed", stages, assigned, "Execution stage failed.")

        review_sections = [("Plan", plan.summary), ("Executor report", execution.summary)]
        reviews = _run_reviews(parent_agent, assigned, task_text, review_sections, rnd, runner)
        stages.extend(reviews)

        requested = [r for r in reviews if r.verdict != "approved"]
        if not requested:
            verdict = "approved"
            break
        if rnd > max_rounds:
            break
        feedback = "\n\n".join(
            f"### {_ROLE_BY_ID[r.role].title}\n{r.summary or r.error or 'no verdict returned'}"
            for r in requested
        )

    note = (
        "All reviewers approved."
        if verdict == "approved"
        else f"Reviewers still request changes after {rnd} round(s); see the latest findings."
    )
    return _report(verdict, stages, assigned, note)


def _run_reviews(
    parent_agent: Any,
    assigned: Dict[str, Assignment],
    task_text: str,
    sections: Sequence[Tuple[str, str]],
    rnd: int,
    runner: ChildRunner,
) -> List[StageResult]:
    """Run reviewer and verifier concurrently — both are read-only."""
    roles = ("reviewer", "verifier")
    goals = {r: _stage_goal(_ROLE_BY_ID[r], task_text, sections) for r in roles}
    with ThreadPoolExecutor(max_workers=len(roles), thread_name_prefix="orchestrator-review") as pool:
        futures = {
            r: pool.submit(contextvars.copy_context().run, _safe_run, runner, parent_agent, assigned[r], goals[r])
            for r in roles
        }
        return [_to_stage(r, rnd, assigned[r], futures[r].result()) for r in roles]


# Earlier rounds were already fed back to the executor; the report only needs
# their gist, keeping the tool result bounded however many rounds ran.
_SUPERSEDED_SUMMARY_CHARS = 600


def _report(verdict: str, stages: List[StageResult], assigned: Dict[str, Assignment], note: str) -> dict:
    last_round = max((s.round for s in stages), default=0)
    out = []
    for stage in stages:
        d = stage.to_dict()
        if 0 < stage.round < last_round:
            d["summary"] = _clip(stage.summary, _SUPERSEDED_SUMMARY_CHARS)
        out.append(d)
    return {
        "success": verdict == "approved",
        "verdict": verdict,
        "note": note,
        "rounds": max((s.round for s in stages if s.role == "executor"), default=0),
        "models": {r: a.to_dict() for r, a in assigned.items()},
        "stages": out,
    }


__all__ = [
    "Assignment",
    "Candidate",
    "ROLES",
    "ROLE_IDS",
    "auto_assign",
    "gather_candidates",
    "is_enabled",
    "load_orchestrator_config",
    "normalize_config",
    "parse_verdict",
    "resolve_assignments",
    "run_flow",
    "score_candidate",
]
