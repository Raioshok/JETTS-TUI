"""Behavior tests for Google Antigravity OAuth (jettstui/antigravity_auth.py)."""

from __future__ import annotations

import time
from urllib.parse import parse_qs, urlparse

import pytest

import jettstui.antigravity_auth as ag
from jettstui.auth import AuthError, get_auth_status, resolve_provider


def _seed_state(**overrides):
    state = {
        "access_token": "old-token",
        "refresh_token": "refresh-1",
        "expires_at_ms": int((time.time() + 3600) * 1000),
        "email": "user@example.com",
        "project_id": "proj-1",
        "tier_id": "g1-ultra-tier",
    }
    state.update(overrides)
    ag._save_state(state, set_active=True)
    return state


def test_authorize_url_requests_offline_pkce_for_registered_redirect():
    verifier = ag._code_verifier()
    url = ag.build_authorize_url(state="nonce", code_challenge=ag._code_challenge(verifier))
    params = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}

    assert params["redirect_uri"] == ag.ANTIGRAVITY_REDIRECT_URI
    assert params["code_challenge_method"] == "S256"
    assert params["code_challenge"] != verifier
    assert params["access_type"] == "offline"
    assert params["state"] == "nonce"
    assert set(ag.ANTIGRAVITY_OAUTH_SCOPES) == set(params["scope"].split())


@pytest.mark.parametrize("raw,code,state", [
    ("http://localhost:51121/oauth-callback?code=abc&state=xyz", "abc", "xyz"),
    ("code=abc&state=xyz", "abc", "xyz"),
    ("abc", "abc", None),
    ("", None, None),
])
def test_parse_redirect_input_accepts_url_query_or_bare_code(raw, code, state):
    parsed = ag.parse_redirect_input(raw)
    assert parsed["code"] == code
    assert parsed["state"] == state


def test_sign_in_works_out_of_the_box_and_env_overrides_the_client(monkeypatch):
    monkeypatch.delenv("ANTIGRAVITY_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("ANTIGRAVITY_OAUTH_CLIENT_SECRET", raising=False)
    default_id, default_secret = ag.oauth_client_credentials()
    assert default_id.endswith(".apps.googleusercontent.com") and default_secret
    assert parse_qs(urlparse(ag.start_login()["auth_url"]).query)["client_id"] == [default_id]

    monkeypatch.setenv("ANTIGRAVITY_OAUTH_CLIENT_ID", "mine.apps.googleusercontent.com")
    monkeypatch.setenv("ANTIGRAVITY_OAUTH_CLIENT_SECRET", "my-secret")
    assert ag.oauth_client_credentials() == ("mine.apps.googleusercontent.com", "my-secret")


def test_resolve_without_login_requires_relogin():
    with pytest.raises(AuthError) as exc_info:
        ag.resolve_antigravity_runtime_credentials()
    assert exc_info.value.relogin_required


def test_resolve_refreshes_expiring_token_and_persists_it(monkeypatch):
    _seed_state(expires_at_ms=int(time.time() * 1000))
    calls = []

    def fake_refresh(refresh_token, **_):
        calls.append(refresh_token)
        return {"access_token": "new-token", "expires_in": 3600}

    monkeypatch.setattr(ag, "refresh_access_token", fake_refresh)
    creds = ag.resolve_antigravity_runtime_credentials()

    assert creds["api_key"] == "new-token"
    assert creds["project_id"] == "proj-1"
    assert calls == ["refresh-1"]
    # Persisted: a second resolve does not refresh again.
    assert ag.resolve_antigravity_runtime_credentials()["api_key"] == "new-token"
    assert calls == ["refresh-1"]


def test_resolve_discovers_missing_project(monkeypatch):
    _seed_state(project_id="")
    monkeypatch.setattr(ag, "discover_project", lambda token, **_: {"project_id": "found", "tier_id": "g1-pro-tier"})
    assert ag.resolve_antigravity_runtime_credentials()["project_id"] == "found"
    assert ag.get_antigravity_auth_status()["plan"] == "Google AI Pro"


def test_discover_project_onboards_when_account_has_no_project(monkeypatch):
    class _Resp:
        def __init__(self, payload):
            self.status_code = 200
            self._payload = payload
            self.text = ""

        def json(self):
            return self._payload

    def fake_post(client, endpoint, method, token, body):
        if method == "loadCodeAssist":
            return _Resp({"allowedTiers": [{"id": "free-tier", "isDefault": True}]})
        assert method == "onboardUser" and body["tierId"] == "free-tier"
        return _Resp({"done": True, "response": {"cloudaicompanionProject": {"id": "onboarded"}}})

    monkeypatch.setattr(ag, "_post_v1internal", fake_post)
    assert ag.discover_project("tok") == {"project_id": "onboarded", "tier_id": "free-tier"}


@pytest.mark.parametrize("tier,plan", [
    ("g1-ultra-tier", "Google AI Ultra"),
    ("g1-pro-tier", "Google AI Pro"),
    ("free-tier", "Free"),
])
def test_describe_tier_names_the_google_ai_plan(tier, plan):
    assert ag.describe_tier(tier) == plan


def test_logged_in_account_is_reported_and_resolvable_by_alias():
    _seed_state()
    assert get_auth_status("antigravity")["logged_in"] is True
    assert resolve_provider("google-antigravity") == "antigravity"


@pytest.mark.parametrize("raw", [
    "4%2F0AbCd-ef",                                                     # copied from the address bar
    "  4/0AbCd-ef \n",                                                  # stray whitespace
    "\"4/0AbCd-ef\"",                                                   # quoted
    "http://localhost:51121/oauth-callback?state=s&code=4%2F0AbCd-ef&scope=x",
    "http://localhost:51121/oauth-callback#state=s&code=4%2F0AbCd-ef",  # params in the fragment
])
def test_pasted_code_is_normalised_to_the_real_code(raw):
    assert ag.parse_redirect_input(raw)["code"] == "4/0AbCd-ef"


def test_callback_page_shows_the_code_to_copy_and_escapes_it():
    page = ag.render_callback_page(code="4/0Ab<script>", error=None)
    assert 'id="code"' in page and 'id="copy"' in page
    assert "4/0Ab&lt;script&gt;" in page and "4/0Ab<script>" not in page
    assert 'id="code"' not in ag.render_callback_page(code="4/x", error=None, stale=True)
    assert 'id="code"' not in ag.render_callback_page(code=None, error="access_denied")


def test_loopback_listener_is_exclusive_and_ignores_other_attempts():
    import httpx

    try:
        listener = ag.LoopbackListener(expected_state="current")
    except AuthError:
        pytest.skip("port 51121 is in use on this machine")
    try:
        with pytest.raises(AuthError):
            ag.LoopbackListener(expected_state="other")

        base = f"http://127.0.0.1:{ag.ANTIGRAVITY_REDIRECT_PORT}{ag.ANTIGRAVITY_REDIRECT_PATH}"
        stale = httpx.get(f"{base}?code=4%2Fold&state=earlier", timeout=5)
        assert "expired" in stale.text and not listener.done

        fresh = httpx.get(f"{base}?code=4%2Fnew&state=current", timeout=5)
        assert "4/new" in fresh.text
        result = listener.wait(5)
        assert result["code"] == "4/new" and result["state"] == "current"
    finally:
        listener.close()
