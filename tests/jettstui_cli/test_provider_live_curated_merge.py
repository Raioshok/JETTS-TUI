"""Contract tests for endpoint-authoritative provider model discovery."""

from unittest.mock import MagicMock, patch

from jettstui.models import provider_model_ids


class TestGenericProviderLiveCatalog:
    """A successful provider endpoint outranks every bundled preset."""

    @staticmethod
    def _make_profile(models=None):
        profile = MagicMock()
        profile.auth_type = "api_key"
        profile.base_url = "https://api.example.com/v1"
        profile.fetch_models.return_value = models
        profile.fallback_models = None
        return profile

    def _discover(self, provider, live, curated):
        profile = self._make_profile(live)
        with (
            patch("providers.get_provider_profile", return_value=profile),
            patch(
                "jettstui.auth.resolve_api_key_provider_credentials",
                return_value={"api_key": "k", "base_url": ""},
            ),
            patch.dict(
                "jettstui.models._PROVIDER_MODELS",
                {provider: curated},
            ),
        ):
            return provider_model_ids(provider)

    def test_live_catalog_is_not_restricted_or_padded_by_presets(self):
        result = self._discover(
            "zai",
            ["glm-5", "glm-6-preview"],
            ["glm-5.2", "glm-5.1", "glm-5"],
        )

        assert result == ["glm-5", "glm-6-preview"]

    def test_live_order_is_preserved_for_aggregators(self):
        live = ["nemotron-3-ultra-free", "gpt-5.5", "claude-fable-5"]
        result = self._discover(
            "opencode-zen",
            live,
            ["gpt-5.5", "claude-fable-5", "retired-model"],
        )

        assert result == live

    def test_case_insensitive_dedup_preserves_endpoint_casing(self):
        result = self._discover(
            "zai",
            ["GLM-5.1", "glm-5", "glm-5.1", "GLM-5", ""],
            ["glm-4.5"],
        )

        assert result == ["GLM-5.1", "glm-5"]

    def test_profile_fallback_is_used_only_when_endpoint_fails(self):
        profile = self._make_profile(None)
        profile.fallback_models = ("fallback-a", "fallback-b")

        with (
            patch("providers.get_provider_profile", return_value=profile),
            patch(
                "jettstui.auth.resolve_api_key_provider_credentials",
                return_value={"api_key": "k", "base_url": ""},
            ),
            patch.dict(
                "jettstui.models._PROVIDER_MODELS",
                {"new-provider": []},
            ),
        ):
            result = provider_model_ids("new-provider")

        assert result == ["fallback-a", "fallback-b"]
