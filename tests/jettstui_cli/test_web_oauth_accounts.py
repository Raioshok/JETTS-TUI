"""Desktop/dashboard multi-account sign-in and switching (jettstui.web_server)."""

from __future__ import annotations

import io
import json
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from jettstui import oauth_accounts
from jettstui.web_server import _SESSION_TOKEN, app

client = TestClient(app)
HEADERS = {"X-JettsTUI-Session-Token": _SESSION_TOKEN}


def _anthropic_sign_in(*, add_account: bool, token: str) -> None:
    url = "/api/providers/oauth/anthropic/start" + ("?add_account=true" if add_account else "")
    start = client.post(url, headers=HEADERS)
    assert start.status_code == 200, start.text
    body = json.dumps({"access_token": token, "refresh_token": f"r-{token}", "expires_in": 3600}).encode()
    with patch("urllib.request.urlopen", return_value=io.BytesIO(body)):
        done = client.post(
            "/api/providers/oauth/anthropic/submit",
            headers=HEADERS,
            json={"session_id": start.json()["session_id"], "code": "code#state"},
        )
    assert done.json() == {"ok": True, "status": "approved"}, done.text


def _accounts(provider: str) -> list:
    resp = client.get(f"/api/providers/oauth/{provider}/accounts", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()["accounts"]


def test_add_account_sign_in_keeps_the_first_account_and_switches_to_the_new_one():
    _anthropic_sign_in(add_account=False, token="sk-ant-oat01-first")
    before = _accounts("anthropic")
    _anthropic_sign_in(add_account=True, token="sk-ant-oat01-second")
    after = _accounts("anthropic")

    assert len(after) == len(before) + 1
    added = next(a for a in after if a["id"] not in {b["id"] for b in before})
    assert added["active"] and added["source"] == "manual:jettstui_pkce"
    assert sum(a["active"] for a in after) == 1

    listed = client.get("/api/providers/oauth", headers=HEADERS).json()["providers"]
    anthropic = next(p for p in listed if p["id"] == "anthropic")
    assert anthropic["supports_accounts"] and anthropic["account_count"] == len(after)


def test_repeated_plain_sign_in_replaces_the_dashboard_entry_instead_of_stacking():
    _anthropic_sign_in(add_account=False, token="sk-ant-oat01-one")
    _anthropic_sign_in(add_account=False, token="sk-ant-oat01-two")
    dashboard = [a for a in _accounts("anthropic") if a["source"] == "manual:dashboard_pkce"]
    assert len(dashboard) == 1


def test_use_switches_accounts_and_marks_live_sessions_for_rebind():
    for label in ("work", "personal"):
        oauth_accounts.add_pooled_oauth_account(
            "minimax-oauth", access_token=f"tok-{label}", source="manual:minimax_oauth",
            label=label, use_now=False,
        )
    target = next(a for a in _accounts("minimax-oauth") if a["label"] == "personal")

    from tui_gateway import server as gateway

    before = gateway._account_switch_generation.get("minimax-oauth", 0)
    resp = client.post(f"/api/providers/oauth/minimax-oauth/accounts/{target['id']}/use", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    assert resp.json()["account"]["active"] is True
    assert gateway._account_switch_generation["minimax-oauth"] == before + 1
    assert [a["label"] for a in _accounts("minimax-oauth") if a["active"]] == ["personal"]


def test_live_agent_rebinds_to_the_switched_account_on_its_next_turn():
    for label in ("work", "personal"):
        oauth_accounts.add_pooled_oauth_account(
            "minimax-oauth", access_token=f"tok-{label}", source="manual:minimax_oauth",
            label=label, use_now=False,
        )
    from agent.credential_pool import load_pool
    from tui_gateway import server as gateway

    swapped = []
    agent = SimpleNamespace(
        provider="minimax-oauth",
        _credential_pool=load_pool("minimax-oauth"),
        _credential_pool_entry_id=load_pool("minimax-oauth").select().id,
        _swap_credential=lambda entry: swapped.append(entry.label),
    )
    session: dict = {}
    gateway._rebind_switched_account(session, agent)  # nothing switched yet
    assert swapped == []

    oauth_accounts.use_account("minimax-oauth", "personal")
    gateway.note_account_switch("minimax-oauth")
    gateway._rebind_switched_account(session, agent)
    gateway._rebind_switched_account(session, agent)  # same generation: no-op
    assert swapped == ["personal"]


def test_remove_and_unknown_accounts():
    added = oauth_accounts.add_pooled_oauth_account(
        "minimax-oauth", access_token="tok-x", source="manual:minimax_oauth", label="x", use_now=False,
    )
    resp = client.delete(f"/api/providers/oauth/minimax-oauth/accounts/{added['id']}", headers=HEADERS)
    assert resp.status_code == 200 and resp.json()["label"] == "x"
    assert _accounts("minimax-oauth") == []

    missing = client.post("/api/providers/oauth/minimax-oauth/accounts/nope/use", headers=HEADERS)
    assert missing.status_code == 400
    unsupported = client.get("/api/providers/oauth/openrouter/accounts", headers=HEADERS)
    assert unsupported.status_code == 400
    unauthenticated = client.post(f"/api/providers/oauth/minimax-oauth/accounts/{added['id']}/use")
    assert unauthenticated.status_code in {401, 403}


def test_usage_tab_reports_the_quota_of_the_account_in_use():
    _anthropic_sign_in(add_account=False, token="sk-ant-oat01-first")
    _anthropic_sign_in(add_account=True, token="sk-ant-oat01-second")

    seen = []

    def fake_usage(provider, *, base_url=None, api_key=None):
        seen.append((provider, api_key))
        return None

    with patch("agent.account_usage.fetch_account_usage", side_effect=fake_usage):
        rows = client.get("/api/providers/quota", headers=HEADERS).json()["providers"]

    anthropic = next(r for r in rows if r["id"] == "anthropic")
    assert anthropic["account_count"] >= 2
    assert anthropic["account"] == next(a["label"] for a in _accounts("anthropic") if a["active"])
    assert ("anthropic", "sk-ant-oat01-second") in seen
