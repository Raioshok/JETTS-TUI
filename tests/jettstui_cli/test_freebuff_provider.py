"""Tests for Freebuff provider and 1-hour free model session integration."""

import json
from unittest.mock import MagicMock, patch

import pytest

import model_tools  # noqa: F401
from jettstui.auth import (
    PROVIDER_REGISTRY,
    AuthError,
    get_auth_status,
    get_freebuff_auth_status,
    resolve_freebuff_runtime_credentials,
    resolve_provider,
)
from jettstui.freebuff_auth import (
    admit_freebuff_session,
    get_or_create_freebuff_session,
    poll_freebuff_login_status,
    request_freebuff_device_code,
    run_freebuff_oauth_login,
)
from jettstui.models import (
    _PROVIDER_ALIASES,
    _PROVIDER_LABELS,
    _PROVIDER_MODELS,
    CANONICAL_PROVIDERS,
    normalize_provider,
)
from jettstui.providers import ALIASES, JETTSTUI_OVERLAYS, _LABEL_OVERRIDES


# =============================================================================
# Provider Registry
# =============================================================================


class TestFreebuffProviderRegistry:
    def test_registered(self):
        assert "freebuff" in PROVIDER_REGISTRY

    def test_name(self):
        assert "Freebuff" in PROVIDER_REGISTRY["freebuff"].name

    def test_auth_type(self):
        assert PROVIDER_REGISTRY["freebuff"].auth_type == "oauth_external"

    def test_inference_base_url(self):
        assert PROVIDER_REGISTRY["freebuff"].inference_base_url == "https://codebuff.com/api/v1"

    def test_api_key_env_vars(self):
        assert PROVIDER_REGISTRY["freebuff"].api_key_env_vars == ("FREEBUFF_API_KEY",)

    def test_base_url_env_var(self):
        assert PROVIDER_REGISTRY["freebuff"].base_url_env_var == "FREEBUFF_BASE_URL"


# =============================================================================
# Aliases & Normalization
# =============================================================================


class TestFreebuffAliases:
    @pytest.mark.parametrize("alias", ["freebuff", "freebuff-oauth", "freebuff-ai", "codebuff"])
    def test_alias_resolves(self, alias):
        assert resolve_provider(alias) == "freebuff"

    @pytest.mark.parametrize("alias", ["freebuff", "freebuff-oauth", "freebuff-ai", "codebuff"])
    def test_models_normalize_provider(self, alias):
        assert normalize_provider(alias) == "freebuff"

    def test_models_aliases_dict(self):
        assert _PROVIDER_ALIASES.get("freebuff-oauth") == "freebuff"
        assert _PROVIDER_ALIASES.get("codebuff") == "freebuff"


# =============================================================================
# Catalog & Models
# =============================================================================


class TestFreebuffModelCatalog:
    def test_provider_models_present(self):
        assert "freebuff" in _PROVIDER_MODELS
        models = _PROVIDER_MODELS["freebuff"]
        assert "deepseek/deepseek-v4-pro" in models
        assert "deepseek/deepseek-v4.1-flash" in models
        assert "openai/gpt-5.6-luna" in models

    def test_canonical_providers_present(self):
        slugs = [p.slug for p in CANONICAL_PROVIDERS]
        assert "freebuff" in slugs

    def test_provider_labels(self):
        assert _PROVIDER_LABELS.get("freebuff") == "Freebuff"


# =============================================================================
# Providers Overlay
# =============================================================================


class TestFreebuffProvidersOverlay:
    def test_overlay_registered(self):
        assert "freebuff" in JETTSTUI_OVERLAYS
        overlay = JETTSTUI_OVERLAYS["freebuff"]
        assert overlay.transport == "openai_chat"
        assert overlay.auth_type == "oauth_external"
        assert overlay.base_url_override == "https://codebuff.com/api/v1"
        assert overlay.base_url_env_var == "FREEBUFF_BASE_URL"

    def test_overlay_aliases(self):
        assert ALIASES.get("freebuff-oauth") == "freebuff"
        assert ALIASES.get("codebuff") == "freebuff"

    def test_label_overrides(self):
        assert _LABEL_OVERRIDES.get("freebuff") == "Freebuff"


# =============================================================================
# Credentials Resolution
# =============================================================================


class TestFreebuffCredentials:
    def test_resolve_from_env(self, monkeypatch):
        monkeypatch.setenv("FREEBUFF_API_KEY", "fb-test-key-12345")
        monkeypatch.delenv("FREEBUFF_BASE_URL", raising=False)
        creds = resolve_freebuff_runtime_credentials()
        assert creds["api_key"] == "fb-test-key-12345"
        assert creds["base_url"] == "https://codebuff.com/api/v1"
        assert creds["source"] == "environment"

    def test_resolve_custom_base_url(self, monkeypatch):
        monkeypatch.setenv("FREEBUFF_API_KEY", "fb-test-key-12345")
        monkeypatch.setenv("FREEBUFF_BASE_URL", "https://custom.freebuff.local/v1")
        creds = resolve_freebuff_runtime_credentials()
        assert creds["base_url"] == "https://custom.freebuff.local/v1"

    def test_auth_status_logged_in(self, monkeypatch):
        monkeypatch.setenv("FREEBUFF_API_KEY", "fb-test-key")
        status = get_freebuff_auth_status()
        assert status["logged_in"] is True
        assert status["configured"] is True

    def test_auth_status_not_logged_in(self, monkeypatch):
        monkeypatch.delenv("FREEBUFF_API_KEY", raising=False)
        with patch("jettstui.auth.get_provider_auth_state", return_value=None):
            status = get_freebuff_auth_status()
            assert status["logged_in"] is False
            assert status["configured"] is False

    def test_get_auth_status_dispatcher(self, monkeypatch):
        monkeypatch.setenv("FREEBUFF_API_KEY", "fb-test-key")
        status = get_auth_status("freebuff")
        assert status["logged_in"] is True


# =============================================================================
# OAuth Device Flow & 1-Hour Session Admission
# =============================================================================


class TestFreebuffOAuthAndAdmission:
    def test_request_device_code_mock(self):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "fingerprintId": "test-fp-1",
            "fingerprintHash": "hash123",
            "loginUrl": "https://freebuff.com/login?auth_code=abc123",
            "expiresAt": 1792210000000,
            "expiresInMs": 3600000,
        }
        mock_client.post.return_value = mock_resp

        data = request_freebuff_device_code(mock_client, fingerprint_id="test-fp-1")
        assert data["fingerprintId"] == "test-fp-1"
        assert "loginUrl" in data

    def test_poll_login_status_success(self):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "user": {
                "id": "usr_123",
                "authToken": "fb_auth_token_xyz",
                "email": "user@example.com",
            }
        }
        mock_client.get.return_value = mock_resp

        user = poll_freebuff_login_status(
            mock_client,
            fingerprint_id="test-fp-1",
            fingerprint_hash="hash123",
            expires_at=1792210000000,
            timeout_seconds=5.0,
        )
        assert user["authToken"] == "fb_auth_token_xyz"
        assert user["email"] == "user@example.com"

    def test_admit_1h_session_mock(self):
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "status": "active",
                "model": "deepseek/deepseek-v4-pro",
                "instanceId": "inst-12345",
            }
            mock_client.post.return_value = mock_resp

            session = admit_freebuff_session(
                auth_token="fb_token_test",
                model="deepseek/deepseek-v4-pro",
                instance_id="inst-12345",
            )
            assert session["status"] == "active"
            assert session["model"] == "deepseek/deepseek-v4-pro"
            assert session["instance_id"] == "inst-12345"
            assert session["expires_at"] > session["admitted_at"]

    def test_get_or_create_freebuff_session_caches(self):
        with patch("jettstui.freebuff_auth.admit_freebuff_session") as mock_admit:
            mock_admit.return_value = {
                "status": "active",
                "instance_id": "inst-cache-1",
                "model": "deepseek/deepseek-v4-pro",
                "admitted_at": 1000.0,
                "expires_at": 4600.0,
            }
            # First call triggers admission
            s1 = get_or_create_freebuff_session("cache_token_1", "deepseek/deepseek-v4-pro")
            assert s1["instance_id"] == "inst-cache-1"
            assert mock_admit.call_count == 1
