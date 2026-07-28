"""Mistral AI provider profile.

Rejects ANY unrecognised body field with 422 "Extra inputs are not permitted".

Endpoint, model ids and quirks verified against the live API.
"""

from providers import register_provider
from providers.base import ProviderProfile


class _MistralProfile(ProviderProfile):
    def build_reasoning_kwargs(self, *, reasoning_config=None, **context):
        """Map FreeIDE's reasoning intent onto what this provider accepts.

        Returns ({api_kwargs}, {extra_body}). Emits nothing when the mapping is
        not certain — a wrong field is a hard 4xx on strict providers, not a
        degraded response.
        """
        return {}, {}


mistral = _MistralProfile(
    name="mistral",
    env_vars=("MISTRAL_API_KEY",),
    display_name="Mistral AI",
    description="Mistral — Devstral and Codestral",
    signup_url="https://console.mistral.ai",
    base_url="https://api.mistral.ai/v1",
    fallback_models=(
        "devstral-2512",
        "codestral-2508",
        "mistral-medium-2604",
        "mistral-large-2512",
    ),
    default_max_tokens=8192,
)

register_provider(mistral)
