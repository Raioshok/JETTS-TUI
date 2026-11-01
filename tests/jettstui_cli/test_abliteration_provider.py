"""Tests for Abliteration provider support — standard direct API provider."""

import pytest

from jettstui.auth import (
    PROVIDER_REGISTRY,
    resolve_provider,
    get_api_key_provider_status,
    resolve_api_key_provider_credentials,
)

_OTHER_PROVIDER_KEYS = (
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY",
    "GOOGLE_API_KEY", "GEMINI_API_KEY", "DASHSCOPE_API_KEY",
    "XAI_API_KEY", "KIMI_API_KEY", "GLM_API_KEY", "ZAI_API_KEY",
    "MINIMAX_API_KEY", "ARCEEAI_API_KEY", "GMI_API_KEY",
    "OPENROUTER_API_KEY", "COPILOT_GITHUB_TOKEN", "GH_TOKEN",
)


class TestAbliterationProviderRegistry:
    """Abliteration's plugin must auto-wire into the auth PROVIDER_REGISTRY."""

    def test_registered(self):
        assert "abliteration" in PROVIDER_REGISTRY

    def test_name(self):
        assert PROVIDER_REGISTRY["abliteration"].name == "Abliteration"

    def test_auth_type(self):
        assert PROVIDER_REGISTRY["abliteration"].auth_type == "api_key"

    def test_inference_base_url(self):
        assert (
            PROVIDER_REGISTRY["abliteration"].inference_base_url
            == "https://api.abliteration.ai/v1"
        )

    def test_api_key_env_vars(self):
        assert PROVIDER_REGISTRY["abliteration"].api_key_env_vars == ("ABLITERATION_API_KEY",)

    def test_base_url_env_var(self):
        assert PROVIDER_REGISTRY["abliteration"].base_url_env_var == "ABLITERATION_BASE_URL"


class TestAbliterationAliases:
    @pytest.mark.parametrize("alias", ["abliteration", "abliteration-ai", "abliterated"])
    def test_alias_resolves(self, alias, monkeypatch):
        for key in _OTHER_PROVIDER_KEYS:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("ABLITERATION_API_KEY", "abliteration-test-12345")
        assert resolve_provider(alias) == "abliteration"


class TestAbliterationCredentials:
    def test_status_configured(self, monkeypatch):
        monkeypatch.setenv("ABLITERATION_API_KEY", "abliteration-test")
        status = get_api_key_provider_status("abliteration")
        assert status["configured"]

    def test_status_not_configured(self, monkeypatch):
        monkeypatch.delenv("ABLITERATION_API_KEY", raising=False)
        status = get_api_key_provider_status("abliteration")
        assert not status["configured"]

    def test_openrouter_key_does_not_make_abliteration_configured(self, monkeypatch):
        """OpenRouter users should NOT see abliteration as configured."""
        monkeypatch.delenv("ABLITERATION_API_KEY", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
        status = get_api_key_provider_status("abliteration")
        assert not status["configured"]

    def test_resolve_credentials(self, monkeypatch):
        monkeypatch.setenv("ABLITERATION_API_KEY", "abliteration-direct-key")
        monkeypatch.delenv("ABLITERATION_BASE_URL", raising=False)
        creds = resolve_api_key_provider_credentials("abliteration")
        assert creds["api_key"] == "abliteration-direct-key"
        assert creds["base_url"] == "https://api.abliteration.ai/v1"

    def test_custom_base_url_override(self, monkeypatch):
        monkeypatch.setenv("ABLITERATION_API_KEY", "abliteration-x")
        monkeypatch.setenv("ABLITERATION_BASE_URL", "https://custom.abliteration.example/v1")
        creds = resolve_api_key_provider_credentials("abliteration")
        assert creds["base_url"] == "https://custom.abliteration.example/v1"


class TestAbliterationProfile:
    """Profile-level catalog contract (via the plugin registry, not auth)."""

    def test_profile_registered(self):
        import model_tools  # noqa: F401  -- triggers plugin discovery
        import providers

        profile = providers.get_provider_profile("abliteration")
        assert profile is not None
        assert profile.base_url == "https://api.abliteration.ai/v1"
        assert len(profile.fallback_models) >= 1

    def test_fetch_models_parses_live_shape(self, monkeypatch):
        """fetch_models handles the OpenAI-compatible {"data": [...]} shape."""
        import model_tools  # noqa: F401
        import providers

        profile = providers.get_provider_profile("abliteration")

        class _FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return (
                    b'{"data": ['
                    b'{"id": "abliterated-model-large-v2", "owned_by": "abliteration"},'
                    b'{"id": "abliterated-model", "owned_by": "abliteration"}'
                    b'], "object": "list"}'
                )

        monkeypatch.setattr(
            "jettstui.urllib_security.open_credentialed_url",
            lambda req, timeout: _FakeResp(),
        )
        models = profile.fetch_models(api_key="abliteration-test")
        assert models == ["abliterated-model-large-v2", "abliterated-model"]


class TestAbliterationModelSwitch:
    """Verify provider resolution and model switching in both CLI and gateway."""

    def test_resolve_provider_full(self):
        from jettstui.providers import resolve_provider_full, get_provider

        pdef = resolve_provider_full("abliteration")
        assert pdef is not None
        assert pdef.id == "abliteration"
        assert pdef.base_url == "https://api.abliteration.ai/v1"
        assert pdef.transport == "openai_chat"

        pdef_alias = resolve_provider_full("abliteration-ai")
        assert pdef_alias is not None
        assert pdef_alias.id == "abliteration"

    def test_switch_model_explicit_provider(self, monkeypatch):
        from jettstui.model_switch import switch_model

        monkeypatch.setenv("ABLITERATION_API_KEY", "abliteration-test-key")
        result = switch_model(
            raw_input="abliterated-model-large-v2",
            current_provider="openai-api",
            current_model="gpt-5.5",
            explicit_provider="abliteration",
        )
        assert result.success is True
        assert result.target_provider == "abliteration"
        assert result.new_model == "abliterated-model-large-v2"
        assert result.base_url == "https://api.abliteration.ai/v1"
        assert result.api_key == "abliteration-test-key"

    def test_gateway_apply_model_switch(self, monkeypatch):
        """Simulate desktop sending 'model abliterated-model-large-v2 --provider abliteration --session'."""
        from tui_gateway.server import _apply_model_switch

        monkeypatch.setenv("ABLITERATION_API_KEY", "abliteration-test-key")
        res = _apply_model_switch(
            sid="test-session",
            session={"agent": None},
            raw_input="abliterated-model-large-v2 --provider abliteration --session",
        )
        assert res["value"] == "abliterated-model-large-v2"
        assert res.get("confirm_required") is False