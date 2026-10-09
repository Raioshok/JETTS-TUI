"""Session-scoped work modes and the Plan-mode mutation guard.

The mode is carried in a ContextVar so parallel sessions do not leak policy
into each other.  It is intentionally not a model tool and does not alter the
system prompt; a short directive is appended to each new user turn instead.
"""

from __future__ import annotations

import contextvars
import json
from pathlib import PurePath
from typing import Any, Dict, Optional


DEFAULT = "default"
PLAN = "plan"
ACCEPT_EDITS = "accept-edits"
VALID_MODES = (DEFAULT, PLAN, ACCEPT_EDITS)
MODE_CYCLE = (DEFAULT, ACCEPT_EDITS, PLAN)

_mode: contextvars.ContextVar[str] = contextvars.ContextVar(
    "jettstui_work_mode", default=DEFAULT
)

_PLAN_READ_TOOLS = frozenset({
    "read_file", "search_files", "web_search", "web_extract",
    "skills_list", "skill_view", "browser_snapshot",
    "browser_get_content", "browser_get_url", "tool_search", "tool_describe",
})


def normalize_mode(value: str) -> Optional[str]:
    aliases = {
        "normal": DEFAULT,
        "default": DEFAULT,
        "plan": PLAN,
        "planning": PLAN,
        "accept": ACCEPT_EDITS,
        "accept-edits": ACCEPT_EDITS,
        "acceptedits": ACCEPT_EDITS,
        "edit": ACCEPT_EDITS,
    }
    return aliases.get(str(value or "").strip().lower())


def set_current_work_mode(value: str):
    return _mode.set(normalize_mode(value) or DEFAULT)


def get_current_work_mode() -> str:
    return _mode.get()


def next_mode(value: str) -> str:
    """Cycle like modern coding CLIs: normal → auto-edit → plan."""
    current = normalize_mode(value) or DEFAULT
    return MODE_CYCLE[(MODE_CYCLE.index(current) + 1) % len(MODE_CYCLE)]


def turn_directive(mode: str) -> str:
    mode = normalize_mode(mode) or DEFAULT
    if mode == PLAN:
        return (
            "[WORK MODE: PLAN]\n"
            "Inspect and reason, but do not implement or mutate project files. "
            "You may write only planning artifacts under .jettstui/plans/ or "
            ".jettstui/specs/. Finish with a plan/spec or a concise question."
        )
    if mode == ACCEPT_EDITS:
        return (
            "[WORK MODE: ACCEPT EDITS]\n"
            "The user authorizes workspace file edits needed for this request. "
            "Proceed without asking before each edit. Existing dangerous-command "
            "and external-action approvals still apply."
        )
    return ""


def decorate_user_message(message: Any, mode: str) -> Any:
    directive = turn_directive(mode)
    if not directive or not isinstance(message, str):
        return message
    return f"{directive}\n\n{message}"


def _planning_path(path_value: Any) -> bool:
    if not isinstance(path_value, str) or not path_value.strip():
        return False
    normalized = path_value.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    # Absolute paths are allowed only when their normalized components contain
    # the workspace-local planning directory marker.
    parts = tuple(part.lower() for part in PurePath(normalized).parts)
    if ".." in parts:
        return False
    for marker in ((".jettstui", "plans"), (".jettstui", "specs")):
        if any(parts[index:index + 2] == marker for index in range(len(parts) - 1)):
            return True
    return False


def maybe_block_tool(tool_name: str, arguments: Dict[str, Any]) -> Optional[str]:
    """Return a JSON error when Plan mode forbids a tool call."""
    if get_current_work_mode() != PLAN:
        return None
    if tool_name in _PLAN_READ_TOOLS:
        return None
    if tool_name == "write_file" and _planning_path(arguments.get("path")):
        return None
    if (
        tool_name == "patch"
        and arguments.get("mode", "replace") == "replace"
        and _planning_path(arguments.get("path"))
    ):
        return None
    return json.dumps({
        "error": (
            f"Plan mode blocked '{tool_name}'. Only read/research tools and "
            "writes under .jettstui/plans/ or .jettstui/specs/ are allowed. "
            "Switch with /mode accept-edits when the plan is approved."
        )
    }, ensure_ascii=False)
