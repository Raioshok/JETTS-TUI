"""Dashboard/desktop sign-in for Google Antigravity (jettstui.web_server)."""

from __future__ import annotations

from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from jettstui.web_server import _SESSION_TOKEN, app

client = TestClient(app)
HEADERS = {"X-JettsTUI-Session-Token": _SESSION_TOKEN}


class _IdleListener:
    """LoopbackListener stand-in: binds nothing, never receives a redirect."""

    def __init__(self, **_kwargs):
        pass

    def wait(self, _timeout, *, should_stop=None):
        return {"code": None, "state": None, "error": None}


def _start(listener=_IdleListener):
    with patch("jettstui.antigravity_auth.LoopbackListener", listener):
        resp = client.post("/api/providers/oauth/antigravity/start", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    state = parse_qs(urlparse(body["auth_url"]).query)["state"][0]
    return body, state


def _poll(session_id):
    return client.get(f"/api/providers/oauth/antigravity/poll/{session_id}", headers=HEADERS).json()


def test_antigravity_is_offered_as_an_in_app_sign_in():
    resp = client.get("/api/providers/oauth", headers=HEADERS)
    entry = next(p for p in resp.json()["providers"] if p["id"] == "antigravity")
    assert entry["flow"] == "pkce"


def test_start_returns_google_authorize_url_not_another_providers():
    body, _state = _start()
    assert body["flow"] == "pkce"
    assert urlparse(body["auth_url"]).netloc == "accounts.google.com"


def test_pasted_redirect_url_completes_sign_in_once():
    body, state = _start()
    completed = []
    with patch("jettstui.antigravity_auth.complete_login",
               side_effect=lambda code, verifier, **_: completed.append(code) or {}):
        url = f"http://localhost:51121/oauth-callback?code=abc&state={state}"
        first = client.post("/api/providers/oauth/antigravity/submit", headers=HEADERS,
                            json={"session_id": body["session_id"], "code": url})
        again = client.post("/api/providers/oauth/antigravity/submit", headers=HEADERS,
                            json={"session_id": body["session_id"], "code": url})

    assert first.json() == {"ok": True, "status": "approved"}
    assert again.json()["status"] == "approved"
    assert completed == ["abc"]
    poll = client.get(f"/api/providers/oauth/antigravity/poll/{body['session_id']}", headers=HEADERS)
    assert poll.json()["status"] == "approved"


def test_redirect_from_another_attempt_is_rejected():
    body, _state = _start()
    with patch("jettstui.antigravity_auth.complete_login") as complete:
        resp = client.post("/api/providers/oauth/antigravity/submit", headers=HEADERS, json={
            "session_id": body["session_id"],
            "code": "http://localhost:51121/oauth-callback?code=abc&state=someone-else",
        })
    assert resp.json()["ok"] is False
    complete.assert_not_called()


def test_starting_again_cancels_the_older_attempt():
    first, _ = _start()
    second, _ = _start()
    assert _poll(first["session_id"])["status"] == "cancelled"
    assert _poll(second["session_id"])["status"] == "pending"


def test_rejected_paste_keeps_the_attempt_open_for_another_paste():
    from jettstui.auth import AuthError

    body, state = _start()
    attempts = []

    def flaky(code, verifier, **_):
        attempts.append(code)
        if len(attempts) == 1:
            raise AuthError("Google did not accept the sign-in code (Malformed auth code).")
        return {}

    with patch("jettstui.antigravity_auth.complete_login", side_effect=flaky):
        bad = client.post("/api/providers/oauth/antigravity/submit", headers=HEADERS,
                          json={"session_id": body["session_id"], "code": "4/0Abad"})
        assert bad.json()["status"] == "pending" and "Malformed" in bad.json()["message"]
        good = client.post("/api/providers/oauth/antigravity/submit", headers=HEADERS,
                           json={"session_id": body["session_id"], "code": "4%2F0Agood"})
    assert good.json() == {"ok": True, "status": "approved"}
    # The address-bar form of the code is URL-decoded before the exchange.
    assert attempts == ["4/0Abad", "4/0Agood"]


def test_start_reports_when_the_redirect_cannot_be_picked_up_automatically():
    from jettstui.auth import AuthError

    class _PortBusy:
        def __init__(self, **_kwargs):
            raise AuthError("Could not listen on http://localhost:51121/oauth-callback")

    body, _ = _start(listener=_PortBusy)
    assert body["loopback"] is False
    ok, _ = _start()
    assert ok["loopback"] is True
