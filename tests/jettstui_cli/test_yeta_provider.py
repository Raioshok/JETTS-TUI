"""Tests for Yeta Platform provider support — standard direct API provider.

Endpoint + models verified against live API on 2026-11-04
(https://platform.yeta.ai/api/pricing).
"""

import pytest

from jettstui.auth import (
    PROVIDER_REGISTRY,
    get_api_key_provider_status,
    resolve_api_key_provider_credentials,
    resolve_provider,
)

_OTHER_PROVIDER_KEYS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "DASHSCOPE_API_KEY",
    "XAI_API_KEY",
    "KIMI_API_KEY",
    "GLM_API_KEY",
    "ZAI_API_KEY",
    "MINIMAX_API_KEY",
    "ARCEEAI_API_KEY",
    "GMI_API_KEY",
    "DAHL_API_KEY",
    "ABLITERATION_API_KEY",
    "OPENROUTER_API_KEY",
    "COPILOT_GITHUB_TOKEN",
    "GH_TOKEN",
)


@pytest.fixture(autouse=True)
def _clear_yeta_env(monkeypatch):
    monkeypatch.delenv("YETA_API_KEY", raising=False)
    monkeypatch.delenv("YETA_BASE_URL", raising=False)


# =============================================================================
# Provider Registry
# =============================================================================


class TestYetaProviderRegistry:
    """Yeta's plugin must auto-wire into the auth PROVIDER_REGISTRY."""

    def test_registered(self):
        assert "yeta" in PROVIDER_REGISTRY

    def test_name(self):
        assert PROVIDER_REGISTRY["yeta"].name == "Yeta Platform"

    def test_auth_type(self):
        assert PROVIDER_REGISTRY["yeta"].auth_type == "api_key"

    def test_inference_base_url(self):
        assert (
            PROVIDER_REGISTRY["yeta"].inference_base_url
            == "https://platform.yeta.ai/v1"
        )

    def test_api_key_env_vars(self):
        assert PROVIDER_REGISTRY["yeta"].api_key_env_vars == ("YETA_API_KEY",)

    def test_base_url_env_var(self):
        assert PROVIDER_REGISTRY["yeta"].base_url_env_var == "YETA_BASE_URL"


# =============================================================================
# Aliases
# =============================================================================


class TestYetaAliases:
    @pytest.mark.parametrize("alias", ["yeta", "yeta-platform", "yeta-ai", "yetaai"])
    def test_alias_resolves(self, alias, monkeypatch):
        for key in _OTHER_PROVIDER_KEYS:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("YETA_API_KEY", "yeta-test-12345")
        assert resolve_provider(alias) == "yeta"

    def test_models_normalize_provider(self):
        from jettstui.models import normalize_provider

        assert normalize_provider("yeta-platform") == "yeta"
        assert normalize_provider("yeta-ai") == "yeta"
        assert normalize_provider("yetaai") == "yeta"

    def test_providers_normalize_provider(self):
        from jettstui.providers import normalize_provider as normalize_provider_in_providers

        assert normalize_provider_in_providers("yeta-platform") == "yeta"
        assert normalize_provider_in_providers("yeta-ai") == "yeta"
        assert normalize_provider_in_providers("yetaai") == "yeta"


# =============================================================================
# Config Registry
# =============================================================================


class TestYetaConfigRegistry:
    def test_optional_env_vars_include_yeta(self):
        from jettstui.config import OPTIONAL_ENV_VARS

        assert "YETA_API_KEY" in OPTIONAL_ENV_VARS
        assert OPTIONAL_ENV_VARS["YETA_API_KEY"]["category"] == "provider"
        assert OPTIONAL_ENV_VARS["YETA_API_KEY"]["password"] is True
        assert OPTIONAL_ENV_VARS["YETA_API_KEY"]["url"] == "https://platform.yeta.ai/"

        assert "YETA_BASE_URL" in OPTIONAL_ENV_VARS
        assert OPTIONAL_ENV_VARS["YETA_BASE_URL"]["category"] == "provider"
        assert OPTIONAL_ENV_VARS["YETA_BASE_URL"]["password"] is False


# =============================================================================
# Credentials
# =============================================================================


class TestYetaCredentials:
    def test_status_configured(self, monkeypatch):
        monkeypatch.setenv("YETA_API_KEY", "yeta-test")
        status = get_api_key_provider_status("yeta")
        assert status["configured"]

    def test_status_not_configured(self, monkeypatch):
        monkeypatch.delenv("YETA_API_KEY", raising=False)
        status = get_api_key_provider_status("yeta")
        assert not status["configured"]

    def test_openrouter_key_does_not_make_yeta_configured(self, monkeypatch):
        """OpenRouter users should NOT see yeta as configured."""
        monkeypatch.delenv("YETA_API_KEY", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
        status = get_api_key_provider_status("yeta")
        assert not status["configured"]

    def test_resolve_credentials(self, monkeypatch):
        monkeypatch.setenv("YETA_API_KEY", "yeta-direct-key")
        monkeypatch.delenv("YETA_BASE_URL", raising=False)
        creds = resolve_api_key_provider_credentials("yeta")
        assert creds["api_key"] == "yeta-direct-key"
        assert creds["base_url"] == "https://platform.yeta.ai/v1"

    def test_custom_base_url_override(self, monkeypatch):
        monkeypatch.setenv("YETA_API_KEY", "yeta-x")
        monkeypatch.setenv("YETA_BASE_URL", "https://custom.yeta.example/v1")
        creds = resolve_api_key_provider_credentials("yeta")
        assert creds["base_url"] == "https://custom.yeta.example/v1"


# =============================================================================
# Model catalog & normalization
# =============================================================================


class TestYetaModelCatalog:
    def test_static_model_list(self):
        from jettstui.models import _PROVIDER_MODELS

        assert "yeta" in _PROVIDER_MODELS
        assert len(_PROVIDER_MODELS["yeta"]) >= 1

    def test_canonical_provider_entry(self):
        from jettstui.models import CANONICAL_PROVIDERS

        slugs = [p.slug for p in CANONICAL_PROVIDERS]
        assert "yeta" in slugs

    def test_in_matching_prefix_strip_set(self):
        from jettstui.model_normalize import _MATCHING_PREFIX_STRIP_PROVIDERS

        assert "yeta" in _MATCHING_PREFIX_STRIP_PROVIDERS

    def test_strips_prefix(self):
        from jettstui.model_normalize import normalize_model_for_provider

        assert (
            normalize_model_for_provider(
                "yeta/deepseek-v4.1-flash", "yeta"
            )
            == "deepseek-v4.1-flash"
        )

    def test_bare_name_unchanged(self):
        from jettstui.model_normalize import normalize_model_for_provider

        assert (
            normalize_model_for_provider("deepseek-v4.1-flash", "yeta")
            == "deepseek-v4.1-flash"
        )


# =============================================================================
# Profile & Discovery
# =============================================================================


class TestYetaProfile:
    def test_profile_registered_with_expected_models(self):
        import model_tools  # noqa: F401  -- triggers plugin discovery
        import providers

        profile = providers.get_provider_profile("yeta")
        assert profile is not None
        assert profile.base_url == "https://platform.yeta.ai/v1"
        assert "deepseek-v4.1-flash" in profile.fallback_models
        assert profile.default_aux_model == "deepseek-v4.1-flash"

    def test_fetch_models_authenticated(self, monkeypatch):
        """fetch_models handles the OpenAI-compatible {"data": [...]} shape."""
        import model_tools  # noqa: F401
        import providers

        profile = providers.get_provider_profile("yeta")

        class _FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return (
                    b'{"data": ['
                    b'{"id": "deepseek-v4.1-flash", "owned_by": "deepseek"},'
                    b'{"id": "glm-5.3-flash", "owned_by": "zhipu"}'
                    b'], "object": "list"}'
                )

        monkeypatch.setattr(
            "jettstui.urllib_security.open_credentialed_url",
            lambda req, timeout: _FakeResp(),
        )
        models = profile.fetch_models(api_key="yeta-test")
        assert models == ["deepseek-v4.1-flash", "glm-5.3-flash"]

    def test_fetch_models_unauthenticated_fallback(self, monkeypatch):
        """fetch_models falls back to /api/pricing when api_key is None."""
        import model_tools  # noqa: F401
        import providers

        profile = providers.get_provider_profile("yeta")

        class _FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return (
                    b'{"data": ['
                    b'{"model_name": "deepseek-v4.1-flash"},'
                    b'{"model_name": "glm-5.3-flash"}'
                    b'], "success": true}'
                )

        monkeypatch.setattr(
            "jettstui.urllib_security.open_credentialed_url",
            lambda req, timeout: _FakeResp(),
        )
        models = profile.fetch_models(api_key=None)
        assert models == ["deepseek-v4.1-flash", "glm-5.3-flash"]


# =============================================================================
# Model Switching & Gateway
# =============================================================================


class TestYetaModelSwitch:
    def test_resolve_provider_full(self):
        from jettstui.providers import resolve_provider_full

        pdef = resolve_provider_full("yeta")
        assert pdef is not None
        assert pdef.id == "yeta"
        assert pdef.base_url == "https://platform.yeta.ai/v1"
        assert pdef.transport == "openai_chat"

        pdef_alias = resolve_provider_full("yeta-ai")
        assert pdef_alias is not None
        assert pdef_alias.id == "yeta"

    def test_switch_model_explicit_provider(self, monkeypatch):
        from jettstui.model_switch import switch_model

        monkeypatch.setenv("YETA_API_KEY", "yeta-test-key")
        result = switch_model(
            raw_input="deepseek-v4.1-flash",
            current_provider="openai-api",
            current_model="gpt-5.5",
            explicit_provider="yeta",
        )
        assert result.success is True
        assert result.target_provider == "yeta"
        assert result.new_model == "deepseek-v4.1-flash"
        assert result.base_url == "https://platform.yeta.ai/v1"
        assert result.api_key == "yeta-test-key"

    def test_gateway_apply_model_switch(self, monkeypatch):
        from tui_gateway.server import _apply_model_switch

        monkeypatch.setenv("YETA_API_KEY", "yeta-test-key")
        res = _apply_model_switch(
            sid="test-session",
            session={"agent": None},
            raw_input="deepseek-v4.1-flash --provider yeta --session",
        )
        assert res["value"] == "deepseek-v4.1-flash"
        assert res.get("confirm_required") is False
