"""Dashboard/desktop sign-in for Google Antigravity (jettstui.web_server)."""

from __future__ import annotations

from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from jettstui.web_server import _SESSION_TOKEN, app

client = TestClient(app)
HEADERS = {"X-JettsTUI-Session-Token": _SESSION_TOKEN}


def _never_called(*_args, **_kwargs):  # loopback listener stand-in
    return {"code": None, "state": None, "error": None}


def _start():
    with patch("jettstui.antigravity_auth._wait_for_loopback_callback", side_effect=_never_called):
        resp = client.post("/api/providers/oauth/antigravity/start", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    state = parse_qs(urlparse(body["auth_url"]).query)["state"][0]
    return body, state


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
