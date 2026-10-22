"""Multi-model orchestrator flow: concurrent plan / execute / review / verify.

Every role runs as an isolated subagent on its own model, and all of them run
AT THE SAME TIME.  Each round has two concurrent phases:

* **work** — the planner drafts and refines the plan, the executor implements
  from it as it fills in, and the reviewer and security & quality verifier
  gather the pieces they need to judge the result (requirements, relevant
  code, a baseline test run) while posting early findings the executor can fix
  before it finishes.
* **verify** — the reviewer (correctness), verifier (security & quality) and
  planner (plan coverage) independently judge the final state and each return
  a verdict.

The agents coordinate through a shared *board*: a per-run directory with one
markdown file per role that each agent writes and the others read.  Any
verdict other than APPROVED loops the findings back for another round (the
executor checks each finding before fixing it), bounded by
``max_review_rounds``.

Config (``orchestrator:`` in config.yaml)::

    orchestrator:
      enabled: false
      max_review_rounds: 2
      auto_balance: balanced        # economy | balanced | quality
      roles:
        planner:  {provider: "", model: ""}   # empty model = Auto
        executor: {provider: "", model: ""}
        reviewer: {provider: "", model: ""}
        verifier: {provider: "", model: ""}

Auto picks a model per role from the user's configured providers by *value*:
estimated quality for the role minus a cost penalty whose weight comes from
``auto_balance`` and how many tokens the role burns.  It prefers a different
model family for the review roles than the one writing the code so the
cross-checks are genuinely independent.

The flow is exposed to the agent as the config-gated ``orchestrate`` tool
(``tools/orchestrator_tool.py``), to the desktop app via the
``orchestrator.get`` / ``orchestrator.save`` RPCs, and streams live
``orchestrator.run`` / ``orchestrator.stage`` progress events that the desktop
Flow sidebar renders.
"""

from __future__ import annotations

import contextvars
import logging
import math
import re
import shutil
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


# ─── Roles ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RoleSpec:
    id: str
    title: str
    # What the role does while everyone works concurrently.
    work_brief: str
    # How the role judges the final state; None = no verify-phase seat.
    verify_brief: Optional[str] = None


_VERDICT_RULE = (
    "Do not modify any project files. End your answer with exactly one line:\n"
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
        "You are the PLANNER. Investigate the codebase and environment, then "
        "write a concrete, numbered implementation plan (files to change, the "
        "approach, edge cases, how to verify) to your board file. The executor "
        "is already working from that file, so write a first draft within your "
        "first few steps and refine it as you learn more. While refining, read "
        "the executor's board file and record any deviation from the plan under "
        "a 'Deviations' heading. Do not modify project files. Finish with the "
        "final plan.",
        "You are the PLANNER, now checking plan coverage. Read the final "
        "changes and confirm every requirement of the task and every plan step "
        "is actually implemented. A missing or partial requirement is a "
        "defect. " + _VERDICT_RULE,
    ),
    RoleSpec(
        "executor",
        "Executor",
        "You are the EXECUTOR. Carry out the task, making the actual changes "
        "and running the relevant checks/tests. Read the planner's board file "
        "before you start and again between major steps — it defines the exact "
        "project directory, targets, and implementation plan. Never assume the "
        "launch directory is the target if the planner or task specifies a different "
        "project. If the task is a continuation or concise directive, the planner's "
        "board file contains the authoritative specification. While it is empty, "
        "investigate the target indicated in the task, but align with the planner's "
        "board as soon as it is posted. After each meaningful step, append what you "
        "changed (files) and what is next to your board file so the reviewers can "
        "follow along. Before you finish, read the reviewer's and verifier's board "
        "files and address every valid early finding; if you believe a finding is "
        "wrong, explain why in your board file instead of changing code. Finish with "
        "a concise summary of what you changed (files), what you verified, and anything "
        "left undone.",
    ),
    RoleSpec(
        "reviewer",
        "Reviewer",
        "You are the REVIEWER. Gather the pieces needed to judge correctness: "
        "the exact requirements, the code paths involved, and the edge cases "
        "that must hold. Write them to your board file early. While the "
        "executor works, keep re-reading its board file and the files it "
        "touched, and post early findings to your board file as numbered items "
        "(file + concrete problem) so they are fixed before the executor "
        "finishes. Do not modify project files. Finish with your notes — no "
        "verdict yet; you judge the final result next.",
        "You are the REVIEWER, now judging the finished changes for correctness "
        "against the task and plan: bugs, missed requirements, broken edge "
        "cases. Use the pieces you gathered, re-read the changed files, and "
        "confirm the executor really addressed earlier findings. "
        + _VERDICT_RULE,
    ),
    RoleSpec(
        "verifier",
        "Security & quality",
        "You are the SECURITY & QUALITY verifier. Establish a baseline: find "
        "the project's tests and linters relevant to the task, run them, and "
        "record the exact commands and results in your board file. Note the "
        "security-sensitive spots the change touches (input handling, secrets, "
        "permissions, injection). While the executor works, re-read its board "
        "file and the files it touched and post early findings to your board "
        "file. Do not modify project files. Finish with your notes — no verdict "
        "yet; you judge the final result next.",
        "You are the SECURITY & QUALITY verifier, now judging the finished "
        "changes. Re-run the tests/linters you baselined against the final "
        "state and inspect the changes for security problems (injection, "
        "secrets, unsafe input handling, permissions) and quality problems "
        "(failing tests or lint, missing error handling, dead code). "
        + _VERDICT_RULE,
    ),
)

ROLE_IDS: Tuple[str, ...] = tuple(r.id for r in ROLES)
_ROLE_BY_ID: Dict[str, RoleSpec] = {r.id: r for r in ROLES}

PHASE_WORK = "work"
PHASE_VERIFY = "verify"
# Everyone works at once; every role with a verify brief judges at once.
WORK_ROLES: Tuple[str, ...] = ROLE_IDS
VERIFY_ROLES: Tuple[str, ...] = tuple(r.id for r in ROLES if r.verify_brief)

DEFAULT_MAX_REVIEW_ROUNDS = 2
MAX_REVIEW_ROUNDS_CAP = 5
# Per-stage summary budget carried between stages.
_STAGE_SUMMARY_CHARS = 8000

BALANCE_MODES: Tuple[str, ...] = ("economy", "balanced", "quality")
DEFAULT_BALANCE = "balanced"


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

    balance = str(section.get("auto_balance") or DEFAULT_BALANCE).strip().lower()
    if balance not in BALANCE_MODES:
        balance = DEFAULT_BALANCE

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
        "auto_balance": balance,
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
    cost_input: float = 0.0
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
    # "$" (cheap) … "$$$$" (premium); "" when the price is unknown.
    cost_tier: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# Name heuristics for models missing from models.dev.
_STRONG_TOKENS = ("opus", "ultra", "-pro", "pro-", "gpt-5", "o3", "o4", "max", "large", "405b", "grok-4", "r1")
_FAST_TOKENS = ("mini", "flash", "haiku", "nano", "lite", "small", "tiny", "8b", "7b", "3b", "1b", "fast", "instant")
_CODER_TOKENS = ("coder", "codex", "code", "sonnet", "devstral")

# How much each role values reasoning and coding fit on top of raw capability.
_ROLE_FIT: Dict[str, Dict[str, float]] = {
    "planner": {"reasoning": 0.12, "coder": 0.03},
    "executor": {"reasoning": 0.05, "coder": 0.12},
    "reviewer": {"reasoning": 0.10, "coder": 0.06},
    "verifier": {"reasoning": 0.10, "coder": 0.06},
}

# Cost weight per balance mode.  With the concave capability curve and convex
# cost curve below, "balanced" lands on mid-tier models unless a premium one
# is clearly better for the role, "economy" on the cheapest capable model and
# "quality" on the strongest.
_BALANCE_LAMBDA: Dict[str, float] = {"economy": 3.0, "balanced": 0.7, "quality": 0.15}

# Share of the flow's spend each role drives: the executor runs the longest
# tool loop; the planner is short but sets direction for everyone.
_ROLE_COST_SENSITIVITY: Dict[str, float] = {
    "planner": 0.75,
    "executor": 1.0,
    "reviewer": 0.85,
    "verifier": 0.9,
}

# Score an Auto review role may give up to stay independent of the executor.
_DIVERSITY_TOLERANCE = 0.2


def _family_of(c: Candidate) -> str:
    """Model lineage for independence checks: "claude-opus" and
    "claude-sonnet" share training lineage, so both map to "claude"."""
    base = (c.family or c.model.rsplit("/", 1)[-1]).lower()
    lineage = re.split(r"[-_:.\s/]", base, maxsplit=1)[0]
    return re.sub(r"\d.*$", "", lineage) or lineage or base


def _name_tier(model: str) -> float:
    name = model.lower()
    if any(t in name for t in _FAST_TOKENS):
        return 0.1
    if any(t in name for t in _STRONG_TOKENS):
        return 0.8
    return 0.45


def _blended_price(c: Candidate) -> float:
    """$/M tokens weighted for agent loops, which re-read far more than they write."""
    if c.cost_output <= 0 and c.cost_input <= 0:
        return 0.0
    cost_in = c.cost_input if c.cost_input > 0 else c.cost_output / 4
    cost_out = c.cost_output if c.cost_output > 0 else c.cost_input * 4
    return (4 * cost_in + cost_out) / 5


def price_tier(c: Candidate) -> float:
    """0..1 position on the price ladder (log scale); name-based when unpriced."""
    price = _blended_price(c)
    if price <= 0:
        return _name_tier(c.model)
    # ~$0.25/M → 0.08, ~$5/M → 0.49, ~$27/M → 0.8, ≥$75/M → 1.
    return max(0.0, min(1.0, math.log10(price * 2 + 1) / math.log10(151)))


def cost_tier_label(c: Candidate) -> str:
    if _blended_price(c) <= 0:
        return ""
    tier = price_tier(c)
    return "$" if tier < 0.25 else "$$" if tier < 0.55 else "$$$" if tier < 0.8 else "$$$$"


def quality_estimate(c: Candidate, role: str) -> float:
    """Expected quality for the role, ~0..1.2.

    Capability rises with the price tier but with diminishing returns, so a
    premium model has to be meaningfully better to justify its price.
    """
    fit = _ROLE_FIT.get(role, _ROLE_FIT["executor"])
    tier = price_tier(c)
    capability = 1 - (1 - tier) ** 2
    reasoning = 1.0 if c.reasoning else (0.5 if c.reasoning is None else 0.0)
    coder = 1.0 if any(t in c.model.lower() for t in _CODER_TOKENS) else 0.0
    context = 0.0
    if c.context_window:
        context = 0.03 if c.context_window >= 128_000 else -0.08 if c.context_window < 32_000 else 0.0
    recency = 0.03 if c.release_date[:4] >= "2026" else 0.0
    return capability + fit["reasoning"] * reasoning + fit["coder"] * coder + context + recency


def cost_estimate(c: Candidate) -> float:
    """Relative spend, 0..1 — convex, so premium tiers cost disproportionately."""
    return price_tier(c) ** 2


def score_candidate(c: Candidate, role: str, balance: str = DEFAULT_BALANCE) -> float:
    """Value of running ``role`` on ``c``: quality minus balance-weighted cost."""
    lam = _BALANCE_LAMBDA.get(balance, _BALANCE_LAMBDA[DEFAULT_BALANCE])
    lam *= _ROLE_COST_SENSITIVITY.get(role, 1.0)
    return quality_estimate(c, role) - lam * cost_estimate(c)


def _usable(c: Candidate) -> bool:
    # Every stage drives tools (file reads at minimum); a model that models.dev
    # says cannot call tools would stall the flow.
    return c.tool_call is not False


_BALANCE_REASON = {
    "economy": "cheapest model that can do this role well",
    "balanced": "best quality for the cost in this role",
    "quality": "strongest model for this role",
}


def auto_assign(
    candidates: Sequence[Candidate],
    fixed: Optional[Dict[str, Tuple[str, str]]] = None,
    roles: Iterable[str] = ROLE_IDS,
    balance: str = DEFAULT_BALANCE,
) -> Dict[str, Assignment]:
    """Pick a model for each role in ``roles`` by quality-for-cost value.

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

        def value(c: Candidate, _role: str = role_id) -> float:
            return score_candidate(c, _role, balance)

        ranked = sorted(pool, key=value, reverse=True)
        best = ranked[0]
        reason = _BALANCE_REASON.get(balance, _BALANCE_REASON[DEFAULT_BALANCE])
        if avoid:
            diverse = [c for c in ranked if _family_of(c) not in avoid]
            # Only trade down for independence when the alternative is close.
            if diverse and value(diverse[0]) >= value(best) - _DIVERSITY_TOLERANCE:
                if _family_of(best) in avoid:
                    reason = f"{reason}; independent of the model that writes the code"
                best = diverse[0]
        picks[role_id] = Assignment(role_id, best.provider, best.model, True, reason, cost_tier_label(best))
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
        cand.cost_input = float(info.cost_input or 0.0)
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
    auto_roles = [r for r in ROLE_IDS if r not in fixed]
    pool: List[Candidate] = []
    if auto_roles or fixed:
        pool = gather_candidates() if candidates is None else list(candidates)

    out: Dict[str, Assignment] = {}
    for r, (prov, model) in fixed.items():
        match = next((c for c in pool if c.provider == prov and c.model == model), None)
        tier = cost_tier_label(match) if match else ""
        out[r] = Assignment(r, prov, model, False, "chosen by you", tier)
    if auto_roles:
        out.update(auto_assign(pool, fixed, auto_roles, conf.get("auto_balance", DEFAULT_BALANCE)))
    for role_id in ROLE_IDS:
        out.setdefault(
            role_id, Assignment(role_id, "", "", True, "no other models configured; uses the session's model")
        )
    return {r: out[r] for r in ROLE_IDS}


# ─── Shared board ───────────────────────────────────────────────────────────

# Older run boards are pruned so the directory never grows without bound.
_KEEP_BOARDS = 8


def _boards_root() -> Path:
    from jettstui_constants import get_jettstui_home

    return get_jettstui_home() / "orchestrator" / "runs"


def create_board(run_id: str, task: str) -> Path:
    """Make the run's board: README with the task plus one file per role."""
    try:
        root = _boards_root()
        root.mkdir(parents=True, exist_ok=True)
        board = root / run_id
        board.mkdir()
    except OSError as exc:
        logger.debug("orchestrator: board under JETTSTUI_HOME failed (%s); using temp dir", exc)
        board = Path(tempfile.mkdtemp(prefix=f"jettstui-flow-{run_id}-"))
        root = None
    (board / "README.md").write_text(
        "# Orchestrator board\n\nAll agents run concurrently and coordinate through "
        "these files. Write only to your own role's file; read the others.\n\n"
        f"## Task\n{task.strip()}\n",
        encoding="utf-8",
    )
    for role in ROLES:
        (board / f"{role.id}.md").write_text(f"# {role.title}\n\n(nothing posted yet)\n", encoding="utf-8")
    if root is not None:
        _prune_boards(root)
    return board


def _prune_boards(root: Path) -> None:
    try:
        boards = sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime)
    except OSError:
        return
    for stale in boards[:-_KEEP_BOARDS]:
        shutil.rmtree(stale, ignore_errors=True)


_BOARD_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def read_board(run_id: str, role: str) -> Optional[str]:
    """A role's board file for a run, or None. Only ids/roles we issue resolve."""
    if role not in ROLE_IDS or not _BOARD_ID_RE.match(run_id or ""):
        return None
    try:
        return (_boards_root() / run_id / f"{role}.md").read_text(encoding="utf-8")
    except OSError:
        return None


def _board_section(board: Path, role_id: str) -> str:
    others = ", ".join(f"{board / f'{r}.md'}" for r in ROLE_IDS if r != role_id)
    return (
        f"Shared board directory: {board}\n"
        f"Your board file (write only here): {board / f'{role_id}.md'}\n"
        f"Other agents' board files (read them often): {others}\n"
        "All four agents (planner, executor, reviewer, security & quality "
        "verifier) are running at the same time on different models and check "
        "each other's work through these files."
    )


# ─── Progress events ────────────────────────────────────────────────────────


def _emit(parent_agent: Any, event_type: str, payload: dict) -> None:
    """Relay a display-only flow event through the parent's progress callback."""
    cb = getattr(parent_agent, "tool_progress_callback", None)
    if not callable(cb):
        return
    try:
        cb(event_type, None, None, None, flow=payload)
    except Exception as exc:  # noqa: BLE001 — display must never break the flow
        logger.debug("orchestrator: progress relay failed: %s", exc)


def _short(text: Optional[str], limit: int = 280) -> str:
    line = re.sub(r"\s+", " ", (text or "")).strip()
    return line if len(line) <= limit else line[: limit - 1] + "…"


# ─── Flow runner ────────────────────────────────────────────────────────────


_VERDICT_RE = re.compile(r"VERDICT:\s*(APPROVED|CHANGES[_ ]REQUESTED)", re.IGNORECASE)
_VERDICT_LINE_RE = re.compile(r"^\s*VERDICT:.*$", re.IGNORECASE | re.MULTILINE)


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
    phase: str
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


SpawnHook = Callable[[Optional[str]], None]
ChildRunner = Callable[..., Dict[str, Any]]


def _run_child(
    parent_agent: Any, assignment: Assignment, goal: str, on_spawn: Optional[SpawnHook] = None
) -> Dict[str, Any]:
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
    if on_spawn is not None:
        on_spawn(getattr(child, "_subagent_id", None))
    result = _run_child_lifecycle(0, goal, child, parent_agent)
    result["model"] = getattr(child, "model", None) or assignment.model
    result["provider"] = getattr(child, "provider", None) or assignment.provider
    return result


def _stage_goal(
    role_id: str, phase: str, task: str, board: Optional[Path], sections: Sequence[Tuple[str, str]]
) -> str:
    spec = _ROLE_BY_ID[role_id]
    brief = spec.work_brief if phase == PHASE_WORK else spec.verify_brief
    parts = [f"[{spec.title} · {phase}] {brief}", f"## Task\n{task.strip()}"]
    if board is not None:
        parts.append(f"## Board\n{_board_section(board, role_id)}")
    parts.extend(f"## {title}\n{body}" for title, body in sections if body)
    return "\n\n".join(parts)


def _to_stage(role: str, rnd: int, phase: str, assignment: Assignment, raw: Dict[str, Any]) -> StageResult:
    summary = _clip(raw.get("summary") if isinstance(raw, dict) else "")
    stage = StageResult(
        role=role,
        round=rnd,
        phase=phase,
        provider=str(raw.get("provider") or assignment.provider or ""),
        model=str(raw.get("model") or assignment.model or ""),
        status=str(raw.get("status") or "error"),
        summary=summary,
        error=str(raw.get("error") or ""),
    )
    if phase == PHASE_VERIFY:
        stage.verdict = parse_verdict(summary) if stage.status == "completed" else "unknown"
    return stage


def _safe_run(
    runner: ChildRunner, parent: Any, assignment: Assignment, goal: str, on_spawn: Optional[SpawnHook]
) -> Dict[str, Any]:
    try:
        return runner(parent, assignment, goal, on_spawn=on_spawn)
    except Exception as exc:  # noqa: BLE001 — a failed stage is reported, not raised
        logger.warning("orchestrator stage %s failed: %s", assignment.role, exc)
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}


class _FlowRun:
    """One orchestrate call: board, assignments, live events, phase runner."""

    def __init__(self, parent_agent: Any, task_text: str, conf: dict, assigned: Dict[str, Assignment],
                 runner: ChildRunner, board: Optional[Path]):
        self.parent = parent_agent
        self.task = task_text
        self.conf = conf
        self.assigned = assigned
        self.runner = runner
        self.board = board
        self.run_id = board.name if board is not None else uuid.uuid4().hex[:10]
        self.started_at = time.time()
        self.stages: List[StageResult] = []

    def emit_run(self, status: str, rnd: int, phase: str = "", note: str = "") -> None:
        _emit(self.parent, "orchestrator.run", {
            "run_id": self.run_id,
            "status": status,
            "task": _short(self.task, 400),
            "round": rnd,
            "max_rounds": self.conf["max_review_rounds"] + 1,
            "phase": phase,
            "balance": self.conf.get("auto_balance", DEFAULT_BALANCE),
            "board_dir": str(self.board) if self.board is not None else "",
            "started_at": self.started_at,
            "note": note,
            "assignments": {r: a.to_dict() for r, a in self.assigned.items()},
        })

    def _emit_stage(self, role: str, rnd: int, phase: str, status: str, **extra: Any) -> None:
        a = self.assigned[role]
        payload = {
            "run_id": self.run_id,
            "role": role,
            "round": rnd,
            "phase": phase,
            "status": status,
            "provider": a.provider,
            "model": a.model,
        }
        payload.update({k: v for k, v in extra.items() if v not in (None, "")})
        _emit(self.parent, "orchestrator.stage", payload)

    def _run_one(self, role: str, rnd: int, phase: str, goal: str) -> StageResult:
        def on_spawn(subagent_id: Optional[str]) -> None:
            self._emit_stage(role, rnd, phase, "running", subagent_id=subagent_id)

        self._emit_stage(role, rnd, phase, "running")
        stage = _to_stage(role, rnd, phase, self.assigned[role],
                          _safe_run(self.runner, self.parent, self.assigned[role], goal, on_spawn))
        self._emit_stage(
            role, rnd, phase, stage.status,
            model_used=stage.model, verdict=stage.verdict,
            # The verdict travels as its own field; keep the line out of the gist.
            summary=_short(_VERDICT_LINE_RE.sub("", stage.summary).strip() or stage.error),
            # Full (bounded) report for the sidebar's per-agent detail view.
            report=_clip(stage.summary or stage.error, _EVENT_REPORT_CHARS),
        )
        return stage

    def run_phase(self, phase: str, rnd: int, goals: Dict[str, str]) -> Dict[str, StageResult]:
        """Run every role in ``goals`` concurrently; results keep role order."""
        self.emit_run("running", rnd, phase)
        roles = list(goals)
        with ThreadPoolExecutor(max_workers=len(roles), thread_name_prefix=f"orchestrator-{phase}") as pool:
            futures = {
                r: pool.submit(contextvars.copy_context().run, self._run_one, r, rnd, phase, goals[r])
                for r in roles
            }
            results = {r: futures[r].result() for r in roles}
        self.stages.extend(results[r] for r in roles)
        return results

    def interrupted(self) -> bool:
        return bool(getattr(self.parent, "_interrupt_requested", False))


def run_flow(
    parent_agent: Any,
    task: str,
    context: Optional[str] = None,
    *,
    config: Optional[dict] = None,
    assignments: Optional[Dict[str, Assignment]] = None,
    runner: ChildRunner = _run_child,
    board: Optional[Path] = None,
) -> dict:
    """Run concurrent work + verify phases, looping on requested changes."""
    conf = config if config is not None else load_orchestrator_config()
    assigned = assignments if assignments is not None else resolve_assignments(conf)
    max_rounds = conf["max_review_rounds"]
    task_text = task.strip()
    if context and context.strip():
        task_text = f"{task_text}\n\nContext:\n{context.strip()}"
    if board is None:
        try:
            board = create_board(uuid.uuid4().hex[:10], task_text)
        except OSError as exc:
            logger.warning("orchestrator: no shared board (%s); agents share results between phases only", exc)

    flow = _FlowRun(parent_agent, task_text, conf, assigned, runner, board)
    plan = ""
    feedback = ""
    if board is not None:
        planner_file = board / "planner.md"
        if planner_file.is_file():
            try:
                p_text = planner_file.read_text(encoding="utf-8").strip()
                if p_text and "(nothing posted yet)" not in p_text.lower():
                    plan = p_text
            except OSError:
                pass
        reviewer_file = board / "reviewer.md"
        if reviewer_file.is_file():
            try:
                r_text = reviewer_file.read_text(encoding="utf-8").strip()
                if r_text and "(nothing posted yet)" not in r_text.lower():
                    feedback = r_text
            except OSError:
                pass
    verdict = "changes_requested"
    rnd = 0
    while True:
        rnd += 1
        if flow.interrupted():
            return _finish(flow, "interrupted", "Interrupted before round %d." % rnd)

        # ── Work: everyone at once ──────────────────────────────────────
        work_sections: List[Tuple[str, str]] = []
        if plan:
            work_sections.append(("Plan from the previous round", plan))
        if feedback:
            work_sections.append((
                "Findings from the last verification",
                feedback + "\n\nExecutor: check each finding against the code before fixing it. "
                "Planner: revise the plan to cover them. Reviewers: gather what you need to "
                "confirm each one is resolved.",
            ))
        work = flow.run_phase(PHASE_WORK, rnd, {
            r: _stage_goal(r, PHASE_WORK, task_text, board, work_sections) for r in WORK_ROLES
        })
        if work["executor"].status != "completed":
            return _finish(flow, "failed", "Execution failed in round %d." % rnd)
        if work["planner"].status == "completed" and work["planner"].summary:
            plan = work["planner"].summary
        if flow.interrupted():
            return _finish(flow, "interrupted", "Interrupted after the work phase of round %d." % rnd)

        # ── Verify: every judge at once, against the final state ────────
        verify_goals = {}
        for r in VERIFY_ROLES:
            sections = [("Plan", plan), ("Executor report", work["executor"].summary)]
            if work[r].summary and r != "planner":
                sections.append(("Pieces you gathered while the executor worked", work[r].summary))
            verify_goals[r] = _stage_goal(r, PHASE_VERIFY, task_text, board, sections)
        verify = flow.run_phase(PHASE_VERIFY, rnd, verify_goals)

        requested = [s for s in verify.values() if s.verdict != "approved"]
        if not requested:
            verdict = "approved"
            break
        if rnd > max_rounds:
            break
        feedback = "\n\n".join(
            f"### {_ROLE_BY_ID[s.role].title}\n{s.summary or s.error or 'no verdict returned'}"
            for s in requested
        )

    note = (
        "Every verifier approved."
        if verdict == "approved"
        else f"Verifiers still request changes after {rnd} round(s); see the latest findings."
    )
    return _finish(flow, verdict, note)


# Per-stage report carried on the finished-stage event (Flow sidebar detail).
_EVENT_REPORT_CHARS = 6000

# Report budget: the final round's verdicts and executor report in full-ish,
# its other work notes shorter, and earlier rounds (already fed back) as gist.
_REPORT_LIMITS = {
    (PHASE_VERIFY, None): 4000,
    (PHASE_WORK, "executor"): 4000,
    (PHASE_WORK, None): 1500,
}
_SUPERSEDED_SUMMARY_CHARS = 300


def _report_limit(stage: StageResult, last_round: int) -> int:
    if stage.round < last_round:
        return _SUPERSEDED_SUMMARY_CHARS
    return _REPORT_LIMITS.get((stage.phase, stage.role)) or _REPORT_LIMITS[(stage.phase, None)]


def _finish(flow: _FlowRun, verdict: str, note: str) -> dict:
    report = _report(verdict, flow.stages, flow.assigned, note, flow.board)
    flow.emit_run(verdict, report["rounds"], note=note)
    return report


def _report(
    verdict: str,
    stages: List[StageResult],
    assigned: Dict[str, Assignment],
    note: str,
    board: Optional[Path] = None,
) -> dict:
    last_round = max((s.round for s in stages), default=0)
    out = []
    for stage in stages:
        d = stage.to_dict()
        d["summary"] = _clip(stage.summary, _report_limit(stage, last_round))
        out.append(d)
    return {
        "success": verdict == "approved",
        "verdict": verdict,
        "note": note,
        "rounds": max((s.round for s in stages if s.role == "executor"), default=0),
        "board_dir": str(board) if board is not None else "",
        "models": {r: a.to_dict() for r, a in assigned.items()},
        "stages": out,
    }


__all__ = [
    "Assignment",
    "BALANCE_MODES",
    "Candidate",
    "PHASE_VERIFY",
    "PHASE_WORK",
    "ROLES",
    "ROLE_IDS",
    "VERIFY_ROLES",
    "WORK_ROLES",
    "auto_assign",
    "cost_estimate",
    "create_board",
    "gather_candidates",
    "is_enabled",
    "load_orchestrator_config",
    "normalize_config",
    "parse_verdict",
    "quality_estimate",
    "read_board",
    "resolve_assignments",
    "run_flow",
    "score_candidate",
]
