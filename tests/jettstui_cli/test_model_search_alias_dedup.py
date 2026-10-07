"""Live picker rows retain exact endpoint wire IDs without duplicates."""

from unittest.mock import patch

from jettstui.model_search import model_alias_canonical
from jettstui.models import provider_model_ids


class TestModelAliasCanonical:
    def test_bare_k3_folds_to_public_slug(self):
        assert model_alias_canonical("k3") == "kimi-k3"
        assert model_alias_canonical("K3") == "kimi-k3"

    def test_non_alias_ids_are_identity(self):
        assert model_alias_canonical("kimi-k2.6") == "kimi-k2.6"
        assert model_alias_canonical("GPT-5.4") == "gpt-5.4"
        assert model_alias_canonical("") == ""


class TestPickerMergeAliasDedup:
    def test_live_bare_k3_is_not_replaced_by_curated_alias(self):
        """The successful endpoint response is authoritative, including ``k3``."""
        with (
            patch(
                "jettstui.auth.resolve_api_key_provider_credentials",
                return_value={
                    "api_key": "sk-kimi-x",
                    "base_url": "https://api.kimi.com/coding",
                },
            ),
            patch(
                "providers.base.ProviderProfile.fetch_models",
                return_value=["k3", "kimi-for-coding"],
            ),
        ):
            out = provider_model_ids("kimi-coding")

        k3_rows = [m for m in out if model_alias_canonical(m) == "kimi-k3"]
        assert k3_rows == ["k3"], out
        assert "kimi-for-coding" in out

    def test_live_only_models_unaffected(self):
        """Alias folding must not drop live models without curated twins."""
        with (
            patch(
                "jettstui.auth.resolve_api_key_provider_credentials",
                return_value={
                    "api_key": "sk-kimi-x",
                    "base_url": "https://api.kimi.com/coding",
                },
            ),
            patch(
                "providers.base.ProviderProfile.fetch_models",
                return_value=["kimi-brand-new-live-only"],
            ),
        ):
            out = provider_model_ids("kimi-coding")
        assert "kimi-brand-new-live-only" in out
