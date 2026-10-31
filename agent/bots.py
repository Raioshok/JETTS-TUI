"""Jetts Bots: named AI teammates that live inside one profile.

A bot is a folder under ``$JETTSTUI_HOME/bots/<slug>/``:

* ``bot.yaml`` — ``name``, ``role`` (its job), optional ``model`` / ``provider``,
  and ``session_id`` of its one ongoing conversation.
* ``MEMORY.md`` — the bot's own notes. ``USER.md`` stays in the shared profile
  memories, so every bot knows the same user.

Bots live inside a profile on purpose: profiles are isolated islands, while
teammates should share what they know about the user.

``apply_bot()`` is the single hook that turns an agent into a bot. The role
goes into the per-session *ephemeral* prompt, which is fixed for the life of
the session, so the cached system prompt is never rebuilt mid-conversation.
Removing a bot archives its folder instead of deleting its memory.
"""

from __future__ import annotations

import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from jettstui_constants import get_jettstui_home

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
_MAX_NAME = 60
_MAX_ROLE = 2000
_FIELDS = ("name", "role", "model", "provider", "session_id")
# session_id -> bot for agents made into bots in this process, including
# delegated children that have no bot thread in their lineage.
_session_bots: Dict[str, str] = {}


def bots_dir() -> Path:
    return get_jettstui_home() / "bots"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")[:32].rstrip("-")


def _bot_path(slug: str) -> Path:
    if not _SLUG_RE.match(slug or ""):
        raise ValueError(f"invalid bot id {slug!r}")
    return bots_dir() / slug


def _read(path: Path) -> Dict[str, Any]:
    data = yaml.safe_load((path / "bot.yaml").read_text(encoding="utf-8")) or {}
    bot = {k: data.get(k) for k in _FIELDS}
    bot["id"] = path.name
    return bot


def _roster_changed() -> None:
    """delegate_task's ``bot`` enum lists the roster; drop cached tool schemas."""
    model_tools = sys.modules.get("model_tools")  # no cache exists if it was never loaded
    if model_tools is not None:
        model_tools._clear_tool_defs_cache()


def _write(slug: str, bot: Dict[str, Any]) -> Dict[str, Any]:
    path = _bot_path(slug)
    path.mkdir(parents=True, exist_ok=True)
    data = {k: bot.get(k) for k in _FIELDS if bot.get(k) not in (None, "")}
    tmp = path / "bot.yaml.tmp"
    tmp.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    tmp.replace(path / "bot.yaml")
    _roster_changed()
    return _read(path)


def _clean_text(value: Any, field: str, limit: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"bot {field} is required")
    if len(text) > limit:
        raise ValueError(f"bot {field} is longer than {limit} characters")
    return text


def create_bot(name: str, role: str, model: Optional[str] = None,
               provider: Optional[str] = None) -> Dict[str, Any]:
    name = _clean_text(name, "name", _MAX_NAME)
    slug = slugify(name)
    if not _SLUG_RE.match(slug):
        raise ValueError(f"bot name {name!r} needs at least one letter or digit")
    if (bots_dir() / slug / "bot.yaml").exists():
        raise ValueError(f"a bot named {slug!r} already exists")
    return _write(slug, {
        "name": name,
        "role": _clean_text(role, "role", _MAX_ROLE),
        "model": (model or "").strip() or None,
        "provider": (provider or "").strip() or None,
    })


def get_bot(slug: str) -> Optional[Dict[str, Any]]:
    path = _bot_path(slug)
    return _read(path) if (path / "bot.yaml").is_file() else None


def list_bots() -> List[Dict[str, Any]]:
    root = bots_dir()
    if not root.is_dir():
        return []
    return [_read(p) for p in sorted(root.iterdir())
            if _SLUG_RE.match(p.name) and (p / "bot.yaml").is_file()]


def update_bot(slug: str, **fields: Any) -> Dict[str, Any]:
    bot = get_bot(slug)
    if bot is None:
        raise ValueError(f"no bot named {slug!r}")
    unknown = set(fields) - set(_FIELDS)
    if unknown:
        raise ValueError(f"unknown bot field(s): {sorted(unknown)}")
    if "name" in fields:
        fields["name"] = _clean_text(fields["name"], "name", _MAX_NAME)
    if "role" in fields:
        fields["role"] = _clean_text(fields["role"], "role", _MAX_ROLE)
    return _write(slug, {**bot, **fields})


def remove_bot(slug: str) -> Path:
    """Archive the bot's folder (memory included) and return where it went."""
    path = _bot_path(slug)
    if not (path / "bot.yaml").is_file():
        raise ValueError(f"no bot named {slug!r}")
    dest = bots_dir() / ".archive" / f"{slug}-{int(time.time())}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(dest))
    _roster_changed()
    return dest


def bot_computer() -> Optional[str]:
    """The VM the Bots share as their own computer (``bots.computer``), if set."""
    from jettstui.config import load_config

    return str((load_config().get("bots") or {}).get("computer") or "").strip() or None


def set_bot_computer(name: Optional[str]) -> None:
    from jettstui.config import set_config_value

    set_config_value("bots.computer", (name or "").strip())


def bot_for_session(session_id: Optional[str], db: Any = None) -> Optional[str]:
    """The bot whose thread ``session_id`` is, following compression/branch parents."""
    if session_id in _session_bots:
        return _session_bots[session_id]
    owners = {b["session_id"]: b["id"] for b in list_bots() if b.get("session_id")}
    if not owners or not session_id:
        return None
    if db is None:
        from jettstui_state import SessionDB

        db = SessionDB()
    current, hops = session_id, 0
    while current and hops < 50:
        if current in owners:
            return owners[current]
        row = db.get_session(current)
        current, hops = (row or {}).get("parent_session_id"), hops + 1
    return None


def bot_usage(slug: str, db: Any = None) -> Dict[str, float]:
    """Cost and tokens of the Bot's thread and everything descended from it.

    shortcut: routines (cron) and handoffs from other chats run in sessions that
    aren't descendants of the thread, so they aren't counted; tag those sessions
    with the bot if per-Bot billing has to be exact.
    """
    usage = {"cost_usd": 0.0, "cost_usd_week": 0.0, "tokens": 0}
    bot = get_bot(slug)
    root = (bot or {}).get("session_id")
    if not root:
        return usage
    if db is None:
        from jettstui_state import SessionDB

        db = SessionDB(read_only=True)
    cost = "COALESCE(NULLIF(actual_cost_usd, 0), estimated_cost_usd, 0)"
    with db._lock:
        row = db._conn.execute(
            f"""WITH RECURSIVE thread(id) AS (
                    SELECT ? UNION SELECT s.id FROM sessions s JOIN thread t ON s.parent_session_id = t.id)
                SELECT COALESCE(SUM({cost}), 0),
                       COALESCE(SUM(CASE WHEN started_at >= ? THEN {cost} END), 0),
                       COALESCE(SUM(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0)), 0)
                FROM sessions WHERE id IN thread""",
            (root, time.time() - 7 * 86400),
        ).fetchone()
    usage.update(cost_usd=float(row[0]), cost_usd_week=float(row[1]), tokens=int(row[2]))
    return usage


def bot_prompt(bot: Dict[str, Any], computer: Optional[str] = None) -> str:
    prompt = (
        f"You are {bot['name']}, one of the user's AI teammates (a Jetts Bot).\n"
        f"Your job: {bot['role']}\n"
        "Work like a teammate: take tasks from start to finish, report what you did "
        "and what is left, keep your memory focused on this job, and stop to ask "
        "before anything irreversible or when you need the user to sign in somewhere."
    )
    if computer:
        prompt += (
            f"\nYour own computer is the virtual machine '{computer}'. computer_use in "
            "this chat drives that machine; the user's desktop is off-limits. When an "
            "app or site needs the user to sign in, say exactly what to sign in to, ask "
            "them to do it on your computer (they open it from the Bots page with "
            "Open computer), and stop until they confirm."
        )
    return prompt


def apply_bot(agent: Any, slug: str) -> Dict[str, Any]:
    """Make ``agent`` act as bot ``slug``. Call before the agent's first turn."""
    bot = get_bot(slug)
    if bot is None:
        raise ValueError(f"no bot named {slug!r}")
    existing = getattr(agent, "ephemeral_system_prompt", None)
    computer = bot_computer() if "computer_use" in (getattr(agent, "valid_tool_names", None) or ()) else None
    agent.ephemeral_system_prompt = "\n\n".join(p for p in (existing, bot_prompt(bot, computer)) if p)
    from tools.memory_tool import MemoryStore

    store = getattr(agent, "_memory_store", None)
    if store is not None:
        bot_store = MemoryStore(
            memory_char_limit=store.memory_char_limit,
            user_char_limit=store.user_char_limit,
            memory_dir=_bot_path(slug),
        )
        bot_store.load_from_disk()
        agent._memory_store = bot_store
    else:
        # Handoffs and routines run without memory by design; they still read the
        # Bot's notes (screened snapshot) so what it learned applies everywhere.
        notes = MemoryStore(memory_dir=_bot_path(slug))
        notes.load_from_disk()
        block = notes.format_for_system_prompt("memory")
        if block:
            agent.ephemeral_system_prompt += (
                "\n\nYour notes from past work (read-only during this task):\n" + block
            )
    agent.jetts_bot = slug
    if getattr(agent, "session_id", None):
        _session_bots[agent.session_id] = slug
    return bot


def delegation_targets() -> List[Dict[str, Any]]:
    """Bots another agent can hand work to (``delegate_task`` ``bot``)."""
    return [{"id": b["id"], "name": b["name"], "role": b["role"]} for b in list_bots()]
