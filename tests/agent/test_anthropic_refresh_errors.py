"""An expired Claude Code login must say why it can't be refreshed, not 'no credentials'."""

from __future__ import annotations

import io
import json
import time
import urllib.error
from unittest.mock import patch

import pytest

from agent import anthropic_adapter as aa


def _http_error(url: str, code: int, body: dict) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, "err", {}, io.BytesIO(json.dumps(body).encode()))


def test_primary_refusal_wins_over_fallback_404_and_keeps_its_reason():
    errors = iter([
        _http_error("primary", 400, {"error": "invalid_grant", "error_description": "Refresh token revoked"}),
        _http_error("fallback", 404, {}),
    ])

    def fake_urlopen(req, timeout=10):
        raise next(errors)

    with patch("urllib.request.urlopen", fake_urlopen), pytest.raises(urllib.error.HTTPError) as caught:
        aa.refresh_anthropic_oauth_pure("rt")
    assert caught.value.code == 400
    assert "invalid_grant: Refresh token revoked" in caught.value.oauth_reason


def test_expired_login_message_names_the_reason_and_the_fix(monkeypatch):
    expired = {"accessToken": "a", "refreshToken": "r", "expiresAt": int((time.time() - 60) * 1000)}
    monkeypatch.setattr(aa, "read_claude_code_credentials", lambda: expired)
    with patch.object(aa, "refresh_anthropic_oauth_pure",
                      side_effect=type("E", (Exception,), {"oauth_reason": "HTTP Error 400 (invalid_grant)"})()):
        assert aa._refresh_oauth_token(expired) is None
    msg = aa.anthropic_missing_credentials_message()
    assert "expired" in msg and "invalid_grant" in msg and "claude /login" in msg


def test_no_login_at_all_keeps_the_setup_instructions(monkeypatch):
    monkeypatch.setattr(aa, "read_claude_code_credentials", lambda: None)
    assert aa.anthropic_missing_credentials_message().startswith("No Anthropic credentials found")
