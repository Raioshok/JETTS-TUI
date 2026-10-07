"""Tests for empty model fallback — when provider is configured but model is missing."""

from unittest.mock import patch


class TestGetDefaultModelForProvider:
    """Unit tests for jettstui.models.get_default_model_for_provider."""

    def test_known_provider_returns_first_model(self):
        from jettstui.models import get_default_model_for_provider
        result = get_default_model_for_provider("openai-codex")
        # Should return first model from _PROVIDER_MODELS["openai-codex"]
        assert result
        assert isinstance(result, str)

    def test_openrouter_returns_preferred_silent_default(self):
        """OpenRouter has no static catalog (live fetch), but the silent
        default must still resolve — to the cost-safe preferred model, never
        the curated list's Anthropic flagship (claude-fable-5)."""
        from jettstui.models import (
            PREFERRED_SILENT_DEFAULT_MODEL,
            get_default_model_for_provider,
        )
        result = get_default_model_for_provider("openrouter")
        assert result == PREFERRED_SILENT_DEFAULT_MODEL
        assert "claude" not in result.lower()

    def test_unknown_provider_returns_empty(self):
        from jettstui.models import get_default_model_for_provider
        assert get_default_model_for_provider("nonexistent-provider") == ""

    def test_custom_provider_returns_empty(self):
        """Custom provider has no model catalog — should return empty."""
        from jettstui.models import get_default_model_for_provider
        # Custom providers don't have entries in _PROVIDER_MODELS
        assert get_default_model_for_provider("some-random-custom") == ""

    def test_openrouter_silent_default_is_not_an_expensive_flagship(self):
        """OpenRouter is metered: the silent fallback (provider set, no model)
        must resolve through the cost-safe silent default, never escalate to a
        flagship. Regression for the billing footgun."""
        from jettstui.models import (
            get_default_model_for_provider,
            get_preferred_silent_default_model,
        )

        result = get_default_model_for_provider("openrouter")
        assert result, "openrouter must resolve to a usable default model"
        assert result == get_preferred_silent_default_model("openrouter")
        assert "opus" not in result.lower(), (
            f"silent default escalated to an expensive flagship: {result!r}"
        )

    def test_catalog_label_overrides_constant(self):
        """A ``"default": true`` label in the cached catalog manifest wins over
        the in-repo constant, so maintainers can rotate the silent default
        without shipping a release."""
        from unittest.mock import patch

        from jettstui import models as models_mod

        with patch(
            "jettstui.model_catalog.get_default_model_from_cache",
            return_value="qwen/qwen3.7-plus",
        ):
            assert (
                models_mod.get_preferred_silent_default_model("openrouter")
                == "qwen/qwen3.7-plus"
            )
            assert (
                models_mod.get_default_model_for_provider("openrouter")
                == "qwen/qwen3.7-plus"
            )

    def test_no_catalog_cache_falls_back_to_constant(self):
        """With no cached manifest (fresh install / offline), the in-repo
        constant is the silent default."""
        from unittest.mock import patch

        from jettstui import models as models_mod

        with patch(
            "jettstui.model_catalog.get_default_model_from_cache",
            return_value=None,
        ):
            assert (
                models_mod.get_preferred_silent_default_model("openrouter")
                == models_mod.PREFERRED_SILENT_DEFAULT_MODEL
            )


class TestDetectStaticProviderCostSafeDefault:
    """detect_static_provider_for_model keeps static-catalog behaviour for
    providers outside the silent-default set."""

    def test_provider_without_override_still_uses_first_model(self):
        """Providers outside _SILENT_DEFAULT_PROVIDERS are unchanged."""
        from jettstui.models import (
            _PROVIDER_MODELS,
            _SILENT_DEFAULT_PROVIDERS,
            detect_static_provider_for_model,
        )

        for provider in ("anthropic", "xai"):
            if provider in _SILENT_DEFAULT_PROVIDERS:
                continue
            result = detect_static_provider_for_model(provider, "openrouter")
            assert result is not None
            assert result[1] == _PROVIDER_MODELS[provider][0]


class TestGatewayEmptyModelFallback:
    """Test that _resolve_session_agent_runtime fills in empty model from provider catalog."""

    def test_empty_model_filled_from_provider(self):
        """When config has no model but provider is openai-codex, use first codex model."""
        from gateway.run import GatewayRunner

        runner = object.__new__(GatewayRunner)
        runner._session_model_overrides = {}

        # Mock _resolve_gateway_model to return empty string
        # Mock _resolve_runtime_agent_kwargs to return openai-codex provider
        with patch("gateway.run._resolve_gateway_model", return_value=""), \
             patch("gateway.run._resolve_runtime_agent_kwargs", return_value={
                 "provider": "openai-codex",
                 "api_key": "test-key",
                 "base_url": "https://chatgpt.com/backend-api/codex",
                 "api_mode": "codex_responses",
             }):
            model, kwargs = runner._resolve_session_agent_runtime()

        # Model should have been filled in from provider catalog
        assert model, "Model should not be empty when provider is known"
        assert isinstance(model, str)
        assert kwargs["provider"] == "openai-codex"

    def test_nonempty_model_not_overridden(self):
        """When config has a model set, don't override it."""
        from gateway.run import GatewayRunner

        runner = object.__new__(GatewayRunner)
        runner._session_model_overrides = {}

        with patch("gateway.run._resolve_gateway_model", return_value="gpt-5.4"), \
             patch("gateway.run._resolve_runtime_agent_kwargs", return_value={
                 "provider": "openai-codex",
                 "api_key": "test-key",
                 "base_url": "https://chatgpt.com/backend-api/codex",
                 "api_mode": "codex_responses",
             }):
            model, kwargs = runner._resolve_session_agent_runtime()

        assert model == "gpt-5.4", "Explicit model should not be overridden"

    def test_empty_model_no_provider_stays_empty(self):
        """When both model and provider are empty, model stays empty."""
        from gateway.run import GatewayRunner

        runner = object.__new__(GatewayRunner)
        runner._session_model_overrides = {}

        with patch("gateway.run._resolve_gateway_model", return_value=""), \
             patch("gateway.run._resolve_runtime_agent_kwargs", return_value={
                 "provider": "",
                 "api_key": "test-key",
                 "base_url": "https://example.com",
                 "api_mode": "chat_completions",
             }):
            model, kwargs = runner._resolve_session_agent_runtime()

        # Can't fill in a default without knowing the provider
        assert model == ""


class TestResolveGatewayModel:
    """Test _resolve_gateway_model reads model from config correctly."""

    def test_returns_default_key(self):
        from gateway.run import _resolve_gateway_model
        assert _resolve_gateway_model({"model": {"default": "gpt-5.4"}}) == "gpt-5.4"

    def test_returns_model_key_fallback(self):
        from gateway.run import _resolve_gateway_model
        assert _resolve_gateway_model({"model": {"model": "gpt-5.4"}}) == "gpt-5.4"

    def test_returns_empty_when_missing(self):
        from gateway.run import _resolve_gateway_model
        assert _resolve_gateway_model({"model": {}}) == ""

    def test_returns_empty_when_no_model_section(self):
        from gateway.run import _resolve_gateway_model
        assert _resolve_gateway_model({}) == ""

    def test_string_model_config(self):
        from gateway.run import _resolve_gateway_model
        assert _resolve_gateway_model({"model": "my-model"}) == "my-model"
