"""Usage tab data: token/cache/cost totals and OAuth provider quota."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

import jettstui.antigravity_auth as ag
from agent.account_usage import AccountUsageSnapshot, AccountUsageWindow, fetch_account_usage
from jettstui.web_server import _SESSION_TOKEN, app

client = TestClient(app)
HEADERS = {"X-JettsTUI-Session-Token": _SESSION_TOKEN}


def test_usage_totals_include_cache_and_cost():
    from jettstui_state import SessionDB

    db = SessionDB()
    try:
        db.create_session(session_id="cached", source="cli", model="claude-sonnet-4-6")
        db.update_token_counts(
            "cached", input_tokens=1000, output_tokens=200, cache_read_tokens=700,
            cache_write_tokens=300, estimated_cost_usd=0.25, api_call_count=2,
        )
    finally:
        db.close()

    data = client.get("/api/analytics/usage?days=7", headers=HEADERS).json()
    totals = data["totals"]
    assert totals["total_cache_read"] == 700
    assert totals["total_cache_write"] == 300
    assert totals["total_estimated_cost"] == 0.25
    model = next(m for m in data["by_model"] if m["model"] == "claude-sonnet-4-6")
    assert model["cache_read_tokens"] == 700
    assert sum(day["cache_write_tokens"] or 0 for day in data["daily"]) == 300


def _catalog(*rows):
    return [{"id": pid, "name": name, "status_fn": None} for pid, name in rows]


def test_quota_lists_signed_in_oauth_providers_and_fetches_supported_ones():
    snapshot = AccountUsageSnapshot(
        provider="antigravity", source="test", fetched_at=datetime.now(timezone.utc),
        plan="Google AI Ultra",
        windows=(AccountUsageWindow(label="Gemini 3 Pro", used_percent=25.0),),
    )
    catalog = _catalog(
        ("antigravity", "Google Antigravity"),
        ("anthropic", "Anthropic API Key"),
        ("claude-code", "Claude OAuth"),
        ("xai-oauth", "xAI Grok"),
        ("minimax-oauth", "MiniMax"),
    )
    logged_in = {"antigravity", "anthropic", "claude-code", "xai-oauth"}
    fetched = []

    def fake_fetch(provider, **_):
        fetched.append(provider)
        return snapshot if provider == "antigravity" else None

    with patch("jettstui.web_server._build_oauth_catalog", return_value=catalog), \
         patch("jettstui.web_server._resolve_provider_status",
               side_effect=lambda pid, _fn: {"logged_in": pid in logged_in}), \
         patch("agent.account_usage.fetch_account_usage", side_effect=fake_fetch):
        providers = client.get("/api/providers/quota", headers=HEADERS).json()["providers"]

    by_id = {p["id"]: p for p in providers}
    # Signed-out providers are left out; both Claude rows share one account.
    assert set(by_id) == {"antigravity", "anthropic", "xai-oauth"}
    assert sorted(fetched) == ["anthropic", "antigravity"]
    assert by_id["antigravity"]["plan"] == "Google AI Ultra"
    assert by_id["antigravity"]["windows"][0] == {
        "label": "Gemini 3 Pro", "used_percent": 25.0, "reset_at": None, "detail": None,
    }
    assert by_id["anthropic"]["error"]
    assert by_id["xai-oauth"]["supported"] is False


def test_antigravity_quota_reports_used_percent_per_model(monkeypatch):
    class _Resp:
        status_code = 200

        def json(self):
            return {"models": {
                "gemini-3-pro-high": {"displayName": "Gemini 3 Pro (High)", "quotaInfo": {
                    "remainingFraction": 0.75, "resetTime": "2026-10-10T12:00:00Z"}},
                "claude-sonnet-4-6": {"quotaInfo": {}},
                "tab_flash_lite": {"quotaInfo": {"remainingFraction": 1}},
            }}

    monkeypatch.setattr(ag, "_post_v1internal", lambda *a, **k: _Resp())
    monkeypatch.setattr(ag, "resolve_antigravity_runtime_credentials",
                        lambda **_: {"api_key": "t", "project_id": "p", "tier_id": "g1-pro-tier"})

    snapshot = fetch_account_usage("antigravity")

    assert snapshot.plan == "Google AI Pro"
    assert [(w.label, w.used_percent) for w in snapshot.windows] == [("Gemini 3 Pro (High)", 25.0)]
    assert snapshot.windows[0].reset_at == datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
