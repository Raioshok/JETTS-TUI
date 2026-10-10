"""Multiple OAuth accounts per provider and fast switching (jettstui/oauth_accounts.py)."""

from __future__ import annotations

import time

import pytest

import jettstui.antigravity_auth as ag
from agent.credential_pool import STATUS_EXHAUSTED, load_pool
from jettstui import oauth_accounts as accounts

POOLED = "minimax-oauth"


def _add(label: str, *, use_now: bool = False) -> dict:
    return accounts.add_pooled_oauth_account(
        POOLED,
        access_token=f"tok-{label}",
        refresh_token=f"refresh-{label}",
        source="manual:minimax_oauth",
        label=label,
        use_now=use_now,
    )


def _active_label(provider: str) -> str:
    return next(a["label"] for a in accounts.list_accounts(provider) if a["active"])


def _sign_in_antigravity(email: str, token: str) -> None:
    ag._save_state(
        {
            "access_token": token,
            "refresh_token": f"refresh-{email}",
            "expires_at_ms": int((time.time() + 3600) * 1000),
            "email": email,
            "project_id": f"proj-{email}",
            "tier_id": "g1-pro-tier",
        },
        set_active=True,
    )


def test_used_account_is_selected_until_it_runs_dry_then_the_pool_rotates():
    _add("first")
    _add("second")
    _add("third")
    assert _active_label(POOLED) == "first"

    accounts.use_account(POOLED, "third")
    assert _active_label(POOLED) == "third"
    # A fresh process (new pool object) honours the pick too.
    assert load_pool(POOLED).select().label == "third"

    pool = load_pool(POOLED)
    pool.select()
    pool.mark_exhausted_and_rotate(status_code=429)
    assert load_pool(POOLED).select().label == "first"
    exhausted = next(a for a in accounts.list_accounts(POOLED) if a["label"] == "third")
    assert exhausted["status"] == "exhausted"

    # Picking a drained account again is an explicit retry: its cooldown lifts.
    accounts.use_account(POOLED, "3")
    assert load_pool(POOLED).select().label == "third"
    assert load_pool(POOLED).entries()[2].last_status != STATUS_EXHAUSTED


def test_auth_reset_lifts_a_cooldown_for_good():
    _add("first")
    _add("second")
    pool = load_pool(POOLED)
    pool.select()
    pool.mark_exhausted_and_rotate(status_code=429)

    assert load_pool(POOLED).reset_statuses() == 1
    # The on-disk cooldown must not be merged back over the reset.
    assert all(a["status"] == "ok" for a in accounts.list_accounts(POOLED))
    assert load_pool(POOLED).select().label == "first"


def test_adding_an_account_with_use_now_switches_to_it_and_removal_clears_the_pin():
    _add("first")
    added = _add("second", use_now=True)
    assert added["active"] and _active_label(POOLED) == "second"

    accounts.remove_account(POOLED, added["id"])
    assert [a["label"] for a in accounts.list_accounts(POOLED)] == ["first"]
    assert load_pool(POOLED).preferred_id is None
    assert _active_label(POOLED) == "first"


def test_unknown_targets_and_providers_are_rejected():
    _add("first")
    with pytest.raises(accounts.AccountError):
        accounts.use_account(POOLED, "nope")
    with pytest.raises(accounts.AccountError):
        accounts.list_accounts("openrouter")
    assert not accounts.supports_accounts("openrouter")


def test_antigravity_keeps_every_signed_in_account_and_switches_the_active_one():
    _sign_in_antigravity("a@example.com", "tok-a")
    _sign_in_antigravity("b@example.com", "tok-b")

    listed = accounts.list_accounts("antigravity")
    assert [a["label"] for a in listed] == ["a@example.com", "b@example.com"]
    assert _active_label("antigravity") == "b@example.com"

    accounts.use_account("antigravity", "a@example.com")
    creds = ag.resolve_antigravity_runtime_credentials()
    assert creds["api_key"] == "tok-a" and creds["project_id"] == "proj-a@example.com"
    assert ag.get_antigravity_auth_status()["account_count"] == 2


def test_antigravity_quota_rotation_puts_the_drained_account_on_cooldown():
    _sign_in_antigravity("a@example.com", "tok-a")
    _sign_in_antigravity("b@example.com", "tok-b")

    switched = ag.rotate_after_quota_exhausted(600)
    assert switched["email"] == "a@example.com"
    drained = next(a for a in ag.list_accounts() if a["email"] == "b@example.com")
    assert drained["exhausted_until"] and drained["exhausted_until"] > time.time()

    # The only other account is cooling down: nothing to switch to.
    assert ag.rotate_after_quota_exhausted(600) is None
    assert ag.resolve_antigravity_runtime_credentials()["api_key"] == "tok-a"


def test_antigravity_refresh_keeps_the_saved_accounts():
    _sign_in_antigravity("a@example.com", "tok-a")
    _sign_in_antigravity("b@example.com", "tok-b")
    state = ag._load_state()
    state["expires_at_ms"] = 0
    ag._save_state(state, set_active=False)

    def fake_refresh(refresh_token, **_):
        return {"access_token": f"fresh-{refresh_token}", "expires_in": 3600}

    original = ag.refresh_access_token
    ag.refresh_access_token = fake_refresh
    try:
        creds = ag.resolve_antigravity_runtime_credentials()
    finally:
        ag.refresh_access_token = original
    assert creds["api_key"] == "fresh-refresh-b@example.com"
    assert len(ag.list_accounts()) == 2


def test_antigravity_single_account_state_migrates_and_removing_active_falls_back():
    # Pre-multi-account layout: one active account, no saved list.
    ag._write_state(
        {"access_token": "tok-old", "refresh_token": "r-old", "email": "old@example.com",
         "expires_at_ms": int((time.time() + 3600) * 1000), "project_id": "p-old"},
        set_active=True,
    )
    assert [a["label"] for a in accounts.list_accounts("antigravity")] == ["old@example.com"]

    _sign_in_antigravity("new@example.com", "tok-new")
    assert len(ag.list_accounts()) == 2
    accounts.remove_account("antigravity", "new@example.com")
    assert _active_label("antigravity") == "old@example.com"
    assert ag.resolve_antigravity_runtime_credentials()["api_key"] == "tok-old"

    accounts.remove_account("antigravity", "old@example.com")
    assert ag.list_accounts() == []
    assert ag.get_antigravity_auth_status()["logged_in"] is False


def test_account_needing_verification_is_flagged_and_skipped_until_picked_again():
    _sign_in_antigravity("a@example.com", "tok-a")
    _sign_in_antigravity("b@example.com", "tok-b")

    switched = ag.rotate_after_verification_required("https://accounts.google.com/verify")
    assert switched["email"] == "a@example.com"
    flagged = next(a for a in accounts.list_accounts("antigravity") if a["label"] == "b@example.com")
    assert flagged["status"] == "verify" and flagged["verify_url"] == "https://accounts.google.com/verify"

    # After verifying in the browser, picking the account clears the flag.
    accounts.use_account("antigravity", "b@example.com")
    picked = next(a for a in accounts.list_accounts("antigravity") if a["label"] == "b@example.com")
    assert picked["active"] and picked["status"] == "ok" and not picked["verify_url"]


def test_only_account_needing_verification_is_flagged_but_stays_active():
    _sign_in_antigravity("solo@example.com", "tok-solo")
    assert ag.rotate_after_verification_required("https://accounts.google.com/verify") is None
    (only,) = accounts.list_accounts("antigravity")
    assert only["active"] and only["status"] == "verify"
    assert ag.resolve_antigravity_runtime_credentials()["api_key"] == "tok-solo"
