"""Multiple sign-in accounts per OAuth provider, with fast switching.

One surface over two storage models:

* Pooled providers (Anthropic, OpenAI Codex, xAI Grok, Qwen, MiniMax) keep each
  account as a credential-pool entry. "Using" an account pins it as the pool's
  preferred entry, which ``CredentialPool.select()`` takes while it is
  available. When the pinned account runs out of quota the pool still rotates
  to the next one automatically.
* Google Antigravity keeps its saved accounts in ``auth.json``
  (``providers.antigravity.accounts``) because the client re-reads the active
  account on every request. "Using" an account rewrites the active one, so live
  sessions switch on their next request.

Used by ``jettstui auth use``, the desktop account switcher (tui_gateway
``accounts.*``), and the dashboard REST endpoints.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

ANTIGRAVITY = "antigravity"
POOLED_ACCOUNT_PROVIDERS = ("anthropic", "openai-codex", "xai-oauth", "qwen-oauth", "minimax-oauth")
ACCOUNT_PROVIDERS = (*POOLED_ACCOUNT_PROVIDERS, ANTIGRAVITY)


class AccountError(ValueError):
    """Unknown provider/account, or an operation the provider does not support."""


def supports_accounts(provider: str) -> bool:
    return (provider or "").strip().lower() in ACCOUNT_PROVIDERS


def _require_provider(provider: str) -> str:
    normalized = (provider or "").strip().lower()
    if normalized not in ACCOUNT_PROVIDERS:
        raise AccountError(f"{provider!r} does not support multiple sign-in accounts.")
    return normalized


def _pool_entry_account(entry: Any, *, active: bool, now: float) -> Dict[str, Any]:
    from agent.credential_pool import STATUS_DEAD, STATUS_EXHAUSTED, _exhausted_until

    status = "ok"
    exhausted_until = None
    if entry.last_status == STATUS_DEAD:
        status = "dead"
    elif entry.last_status == STATUS_EXHAUSTED:
        until = _exhausted_until(entry)
        if until is None or until > now:
            status = "exhausted"
            exhausted_until = until
    return {
        "id": entry.id,
        "label": entry.label or entry.id,
        "detail": entry.auth_type,
        "source": entry.source,
        "active": active,
        "status": status,
        "exhausted_until": exhausted_until,
    }


def list_accounts(provider: str) -> List[Dict[str, Any]]:
    """Display-safe accounts for *provider*; exactly one is ``active`` when any is usable."""
    provider = _require_provider(provider)
    now = time.time()
    if provider == ANTIGRAVITY:
        from jettstui.antigravity_auth import list_accounts as list_antigravity

        return [
            {
                "id": account["id"],
                "label": account["email"] or account["id"],
                "detail": account["plan"],
                "source": "antigravity",
                "active": account["active"],
                "status": "exhausted" if account["exhausted_until"] else "ok",
                "exhausted_until": account["exhausted_until"],
            }
            for account in list_antigravity()
        ]

    from agent.credential_pool import load_pool

    pool = load_pool(provider)
    upcoming = pool.peek()
    upcoming_id = upcoming.id if upcoming is not None else None
    return [
        _pool_entry_account(entry, active=entry.id == upcoming_id, now=now)
        for entry in pool.entries()
    ]


def pinned_pool_credential(provider: str) -> Optional[Any]:
    """The pinned account's (refreshed) pool entry, or ``None`` when nothing is pinned.

    Quota lookups use this so the Usage tab reports the account in use rather
    than whichever login the provider's legacy singleton holds.
    """
    if (provider or "").strip().lower() not in POOLED_ACCOUNT_PROVIDERS:
        return None
    from agent.credential_pool import load_pool

    pool = load_pool(provider)
    if not pool.preferred_id:
        return None
    entry = pool.select()
    return entry if entry is not None and entry.id == pool.preferred_id else None


def _resolve_account_id(provider: str, target: str) -> str:
    """Accept an account id, a 1-based index, or an exact (case-insensitive) label."""
    raw = str(target or "").strip()
    if not raw:
        raise AccountError("No account given.")
    accounts = list_accounts(provider)
    for account in accounts:
        if account["id"] == raw:
            return raw
    matches = [a for a in accounts if str(a["label"]).lower() == raw.lower()]
    if len(matches) == 1:
        return matches[0]["id"]
    if len(matches) > 1:
        raise AccountError(f'More than one {provider} account is labelled "{raw}"; use its number or id.')
    if raw.isdigit() and 1 <= int(raw) <= len(accounts):
        return accounts[int(raw) - 1]["id"]
    raise AccountError(f'No {provider} account matching "{raw}".')


def use_account(provider: str, target: str) -> Dict[str, Any]:
    """Make *target* the account *provider* uses from now on. Returns its display row."""
    provider = _require_provider(provider)
    account_id = _resolve_account_id(provider, target)
    if provider == ANTIGRAVITY:
        from jettstui.antigravity_auth import activate_account

        activate_account(account_id)
    else:
        from agent.credential_pool import load_pool

        if load_pool(provider).set_preferred(account_id) is None:
            raise AccountError(f'No {provider} account matching "{target}".')
    return next(a for a in list_accounts(provider) if a["id"] == account_id)


def remove_account(provider: str, target: str) -> Dict[str, Any]:
    """Forget one account. Returns ``{"label", "cleaned", "hints"}``."""
    provider = _require_provider(provider)
    account_id = _resolve_account_id(provider, target)
    label = next((a["label"] for a in list_accounts(provider) if a["id"] == account_id), account_id)
    if provider == ANTIGRAVITY:
        from jettstui.antigravity_auth import remove_account as remove_antigravity

        remove_antigravity(account_id)
        return {"label": label, "cleaned": [], "hints": []}

    from agent.credential_pool import load_pool
    from agent.credential_sources import find_removal_step
    from jettstui.auth import suppress_credential_source

    pool = load_pool(provider)
    index, _entry, error = pool.resolve_target(account_id)
    if index is None:
        raise AccountError(error or f'No {provider} account matching "{target}".')
    removed = pool.remove_index(index)
    if removed is None:
        raise AccountError(f'No {provider} account matching "{target}".')
    cleaned: List[str] = []
    hints: List[str] = []
    # Same dispatch as `jettstui auth remove`: clean the backing source and
    # suppress it so load_pool() does not re-seed the account.
    step = find_removal_step(provider, removed.source or "")
    if step is not None:
        try:
            result = step.remove_fn(provider, removed)
            cleaned = list(result.cleaned)
            hints = list(result.hints)
            if result.suppress:
                suppress_credential_source(provider, removed.source)
        except Exception:
            suppress_credential_source(provider, removed.source)
    return {"label": label, "cleaned": cleaned, "hints": hints}


def add_pooled_oauth_account(
    provider: str,
    *,
    access_token: str,
    source: str,
    refresh_token: Optional[str] = None,
    expires_at_ms: Optional[int] = None,
    base_url: Optional[str] = None,
    label: Optional[str] = None,
    last_refresh: Optional[str] = None,
    use_now: bool = True,
) -> Dict[str, Any]:
    """Add a self-contained OAuth account to a provider's pool (dashboard "Add account").

    Mirrors ``jettstui auth add``: each account is an independent pool entry
    that refreshes from its own token pair, so adding one never overwrites
    another. With *use_now* the new account becomes the preferred one.
    """
    provider = _require_provider(provider)
    if provider == ANTIGRAVITY:
        raise AccountError("Antigravity accounts are added by signing in; they are not pool entries.")
    from agent.credential_pool import AUTH_TYPE_OAUTH, PooledCredential, label_from_token, load_pool

    pool = load_pool(provider)
    entry = PooledCredential(
        provider=provider,
        id=uuid.uuid4().hex[:6],
        label=(label or "").strip() or label_from_token(access_token, f"{provider}-oauth-{len(pool.entries()) + 1}"),
        auth_type=AUTH_TYPE_OAUTH,
        priority=0,
        source=source,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at_ms=expires_at_ms,
        base_url=base_url,
        last_refresh=last_refresh,
    )
    first = not pool.entries()
    entry = pool.add_entry(entry)
    if use_now:
        pool.set_preferred(entry.id)
    if first:
        from jettstui.auth import mark_provider_active_if_unset

        mark_provider_active_if_unset(provider)
    return next(a for a in list_accounts(provider) if a["id"] == entry.id)
