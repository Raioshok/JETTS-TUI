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
_FIELDS = ("name", "role", "model", "provider", "session_id", "tools", "ask_before")
# Agent-level tools a Bot keeps even with a `tools` allowlist: its memory is the Bot.
_ALWAYS_ALLOWED = frozenset({"memory", "todo", "clarify"})
# session_id -> bot for agents made into bots in this process, including
# delegated children that have no bot thread in their lineage.
_session_bots: Dict[str, str] = {}
# Sessions known not to be a Bot's, so per-tool-call checks stay O(1).
_not_bot_sessions: set = set()


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


def _clean_tool_list(value: Any) -> Optional[List[str]]:
    """A list of tool names from a list or a comma-separated string; None when empty."""
    items = value.split(",") if isinstance(value, str) else list(value or [])
    names = sorted({str(i).strip() for i in items if str(i).strip()})
    for n in names:
        if not re.match(r"^[A-Za-z0-9_.:-]{1,64}$", n):
            raise ValueError(f"not a tool name: {n!r}")
    return names or None


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
    for key in ("tools", "ask_before"):
        if key in fields:
            fields[key] = _clean_tool_list(fields[key])
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


def find_bot(query: str) -> Optional[Dict[str, Any]]:
    """A bot by id, or by name ignoring case (what a user types after /bot)."""
    q = (query or "").strip()
    slug = slugify(q)
    if _SLUG_RE.match(slug or ""):
        bot = get_bot(slug)
        if bot:
            return bot
    return next((b for b in list_bots() if b["name"].lower() == q.lower()), None)


def _chats_path() -> Path:
    return bots_dir() / "chats.json"


def chat_bot(chat_key: str) -> Optional[str]:
    """The bot a messaging chat (gateway session key) talks to, if any."""
    import json

    try:
        slug = json.loads(_chats_path().read_text(encoding="utf-8")).get(chat_key)
    except (OSError, ValueError):
        return None
    return slug if slug and get_bot(slug) else None


def set_chat_bot(chat_key: str, slug: Optional[str]) -> None:
    import json

    path = _chats_path()
    try:
        chats = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        chats = {}
    if slug:
        chats[chat_key] = slug
    else:
        chats.pop(chat_key, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(chats, indent=2), encoding="utf-8")
    tmp.replace(path)


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
    allowed = bot.get("tools")
    if allowed and getattr(agent, "tools", None) is not None:
        # Hide what the Bot can't use; tool_policy() is the actual boundary.
        keep = set(allowed) | _ALWAYS_ALLOWED
        agent.tools = [t for t in agent.tools if t.get("function", {}).get("name") in keep]
        agent.valid_tool_names = {t["function"]["name"] for t in agent.tools}
    agent.jetts_bot = slug
    if getattr(agent, "session_id", None):
        _session_bots[agent.session_id] = slug
        _not_bot_sessions.discard(agent.session_id)
    return bot


def tool_policy(session_id: Optional[str], tool_name: str) -> Optional[tuple]:
    """``("block", why)`` / ``("ask", why)`` for a Bot's tool call, else None.

    Runs on every tool call, so it only considers Bots applied in this process
    and remembers which sessions aren't a Bot's; a compression continuation is
    resolved once through its parents.
    """
    if not session_id or not _session_bots or session_id in _not_bot_sessions:
        return None
    slug = _session_bots.get(session_id)
    if slug is None:
        slug = bot_for_session(session_id)
        if slug is None:
            _not_bot_sessions.add(session_id)
            return None
        _session_bots[session_id] = slug
    bot = get_bot(slug)
    if bot is None:
        return None
    allowed = bot.get("tools")
    if allowed and tool_name not in set(allowed) | _ALWAYS_ALLOWED:
        return ("block", f"{bot['name']} isn't allowed to use {tool_name}. Its tools: {', '.join(allowed)}.")
    if tool_name in (bot.get("ask_before") or []):
        return ("ask", f"{bot['name']} wants to use {tool_name}, which needs your OK for this Bot.")
    return None


def delegation_targets() -> List[Dict[str, Any]]:
    """Bots another agent can hand work to (``delegate_task`` ``bot``)."""
    return [{"id": b["id"], "name": b["name"], "role": b["role"]} for b in list_bots()]
