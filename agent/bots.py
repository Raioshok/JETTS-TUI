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
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from jettstui_constants import get_jettstui_home

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
_MAX_NAME = 60
_MAX_ROLE = 2000
_FIELDS = ("name", "role", "model", "provider", "session_id")


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


def _write(slug: str, bot: Dict[str, Any]) -> Dict[str, Any]:
    path = _bot_path(slug)
    path.mkdir(parents=True, exist_ok=True)
    data = {k: bot.get(k) for k in _FIELDS if bot.get(k) not in (None, "")}
    tmp = path / "bot.yaml.tmp"
    tmp.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    tmp.replace(path / "bot.yaml")
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
    return dest


def bot_for_session(session_id: Optional[str], db: Any = None) -> Optional[str]:
    """The bot whose thread ``session_id`` is, following compression/branch parents."""
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


def bot_prompt(bot: Dict[str, Any]) -> str:
    return (
        f"You are {bot['name']}, one of the user's AI teammates (a Jetts Bot).\n"
        f"Your job: {bot['role']}\n"
        "Work like a teammate: take tasks from start to finish, report what you did "
        "and what is left, keep your memory focused on this job, and stop to ask "
        "before anything irreversible or when you need the user to sign in somewhere."
    )


def apply_bot(agent: Any, slug: str) -> Dict[str, Any]:
    """Make ``agent`` act as bot ``slug``. Call before the agent's first turn."""
    bot = get_bot(slug)
    if bot is None:
        raise ValueError(f"no bot named {slug!r}")
    existing = getattr(agent, "ephemeral_system_prompt", None)
    agent.ephemeral_system_prompt = "\n\n".join(p for p in (existing, bot_prompt(bot)) if p)
    store = getattr(agent, "_memory_store", None)
    if store is not None:
        from tools.memory_tool import MemoryStore

        bot_store = MemoryStore(
            memory_char_limit=store.memory_char_limit,
            user_char_limit=store.user_char_limit,
            memory_dir=_bot_path(slug),
        )
        bot_store.load_from_disk()
        agent._memory_store = bot_store
    agent.jetts_bot = slug
    return bot
