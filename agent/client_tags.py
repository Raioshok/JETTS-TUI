"""Conversation identity shared with provider cache-affinity code.

This compatibility module retains the ambient context API used by the agent
loop and OpenRouter profile. It does not add product, client, or per-session
usage-attribution tags to outbound model requests.
"""

from __future__ import annotations

from contextvars import ContextVar, Token


_conversation_id: ContextVar[str | None] = ContextVar(
    "jetts_tui_conversation_id", default=None
)


def set_conversation_context(conversation_id: str | None) -> Token:
    """Publish the root conversation ID for this execution context."""
    return _conversation_id.set(conversation_id or None)


def reset_conversation_context(token: Token) -> None:
    """Restore the previous context, including after a nested agent call."""
    try:
        _conversation_id.reset(token)
    except ValueError:
        # Cleanup may run in a different copied Context after worker handoff.
        _conversation_id.set(None)


def get_conversation_context() -> str | None:
    """Return the ambient root ID, if any."""
    return _conversation_id.get()
