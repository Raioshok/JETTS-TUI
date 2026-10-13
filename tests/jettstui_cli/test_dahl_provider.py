"""Tests for Dahl Inference provider support — standard direct API provider.

Endpoint + model ids verified against the live API on 2026-10-13
(https://inference.dahl.global/v1/models, keyless).
"""

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


class TestDahlProviderRegistry:
    """Dahl's plugin must auto-wire into the auth PROVIDER_REGISTRY."""

    def test_registered(self):
        assert "dahl" in PROVIDER_REGISTRY

    def test_name(self):
        assert PROVIDER_REGISTRY["dahl"].name == "Dahl Inference"

    def test_auth_type(self):
        assert PROVIDER_REGISTRY["dahl"].auth_type == "api_key"

    def test_inference_base_url(self):
        assert (
            PROVIDER_REGISTRY["dahl"].inference_base_url
            == "https://inference.dahl.global/v1"
        )

    def test_api_key_env_vars(self):
        assert PROVIDER_REGISTRY["dahl"].api_key_env_vars == ("DAHL_API_KEY",)

    def test_base_url_env_var(self):
        assert PROVIDER_REGISTRY["dahl"].base_url_env_var == "DAHL_BASE_URL"


class TestDahlAliases:
    @pytest.mark.parametrize("alias", ["dahl", "dahl-inference", "dahl-ai"])
    def test_alias_resolves(self, alias, monkeypatch):
        for key in _OTHER_PROVIDER_KEYS:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("DAHL_API_KEY", "dahl-test-12345")
        assert resolve_provider(alias) == "dahl"


class TestDahlCredentials:
    def test_status_configured(self, monkeypatch):
        monkeypatch.setenv("DAHL_API_KEY", "dahl-test")
        status = get_api_key_provider_status("dahl")
        assert status["configured"]

    def test_status_not_configured(self, monkeypatch):
        monkeypatch.delenv("DAHL_API_KEY", raising=False)
        status = get_api_key_provider_status("dahl")
        assert not status["configured"]

    def test_openrouter_key_does_not_make_dahl_configured(self, monkeypatch):
        """OpenRouter users should NOT see dahl as configured."""
        monkeypatch.delenv("DAHL_API_KEY", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
        status = get_api_key_provider_status("dahl")
        assert not status["configured"]

    def test_resolve_credentials(self, monkeypatch):
        monkeypatch.setenv("DAHL_API_KEY", "dahl-direct-key")
        monkeypatch.delenv("DAHL_BASE_URL", raising=False)
        creds = resolve_api_key_provider_credentials("dahl")
        assert creds["api_key"] == "dahl-direct-key"
        assert creds["base_url"] == "https://inference.dahl.global/v1"

    def test_custom_base_url_override(self, monkeypatch):
        monkeypatch.setenv("DAHL_API_KEY", "dahl-x")
        monkeypatch.setenv("DAHL_BASE_URL", "https://custom.dahl.example/v1")
        creds = resolve_api_key_provider_credentials("dahl")
        assert creds["base_url"] == "https://custom.dahl.example/v1"


class TestDahlProfile:
    """Profile-level catalog contract (via the plugin registry, not auth)."""

    def test_profile_registered_with_expected_models(self):
        import model_tools  # noqa: F401  -- triggers plugin discovery
        import providers

        profile = providers.get_provider_profile("dahl")
        assert profile is not None
        assert profile.base_url == "https://inference.dahl.global/v1"
        # Contract: the fallback catalog matches the live /v1/models ids.
        assert set(profile.fallback_models) == {
            "MiniMaxAI/MiniMax-M2.7",
            "zai-org/GLM-5.3-Flash",
            "deepseek-ai/DeepSeek-V4-Flash-0731",
        }

    def test_fetch_models_parses_live_shape(self, monkeypatch):
        """fetch_models handles the OpenAI-compatible {"data": [...]} shape."""
        import model_tools  # noqa: F401
        import providers

        profile = providers.get_provider_profile("dahl")

        class _FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return (
                    b'{"data": ['
                    b'{"id": "MiniMaxAI/MiniMax-M2.7", "owned_by": "gonka"},'
                    b'{"id": "zai-org/GLM-5.3-Flash", "owned_by": "gonka"}'
                    b'], "object": "list"}'
                )

        monkeypatch.setattr(
            "jettstui.urllib_security.open_credentialed_url",
            lambda req, timeout: _FakeResp(),
        )
        models = profile.fetch_models(api_key="dahl-test")
        assert models == ["MiniMaxAI/MiniMax-M2.7", "zai-org/GLM-5.3-Flash"]


class TestDahlModelSwitch:
    """Verify provider resolution and model switching in both CLI and gateway."""

    def test_resolve_provider_full(self):
        from jettstui.providers import resolve_provider_full, get_provider

        pdef = resolve_provider_full("dahl")
        assert pdef is not None
        assert pdef.id == "dahl"
        assert pdef.base_url == "https://inference.dahl.global/v1"
        assert pdef.transport == "openai_chat"

        pdef_alias = resolve_provider_full("dahl-inference")
        assert pdef_alias is not None
        assert pdef_alias.id == "dahl"

    def test_switch_model_explicit_provider(self, monkeypatch):
        from jettstui.model_switch import switch_model

        monkeypatch.setenv("DAHL_API_KEY", "dahl-test-key")
        result = switch_model(
            raw_input="MiniMaxAI/MiniMax-M2.7",
            current_provider="openai-api",
            current_model="gpt-5.5",
            explicit_provider="dahl",
        )
        assert result.success is True
        assert result.target_provider == "dahl"
        assert result.new_model == "MiniMaxAI/MiniMax-M2.7"
        assert result.base_url == "https://inference.dahl.global/v1"
        assert result.api_key == "dahl-test-key"

    def test_gateway_apply_model_switch(self, monkeypatch):
        """Simulate desktop sending 'model MiniMaxAI/MiniMax-M2.7 --provider dahl --session'."""
        from tui_gateway.server import _apply_model_switch

        monkeypatch.setenv("DAHL_API_KEY", "dahl-test-key")
        res = _apply_model_switch(
            sid="test-session",
            session={"agent": None},
            raw_input="MiniMaxAI/MiniMax-M2.7 --provider dahl --session",
        )
        assert res["value"] == "MiniMaxAI/MiniMax-M2.7"
        assert res.get("confirm_required") is False