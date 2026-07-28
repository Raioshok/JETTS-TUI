"""Cerebras provider profile.

Strict schema: unknown body fields are a 400, and max_tokens is INVALID (use max_completion_tokens).

Endpoint, model ids and quirks verified against the live API.
"""

from providers import register_provider
from providers.base import ProviderProfile


class _CerebrasProfile(ProviderProfile):
    def build_reasoning_kwargs(self, *, reasoning_config=None, **context):
        """Map FreeIDE's reasoning intent onto what this provider accepts.

        Returns ({api_kwargs}, {extra_body}). Emits nothing when the mapping is
        not certain — a wrong field is a hard 4xx on strict providers, not a
        degraded response.
        """
        if not reasoning_config:
            return {}, {}
        effort = reasoning_config.get("effort") or "medium"
        if effort in ("none", "off"):
            return {"reasoning_effort": "none"}, {}
        return {"reasoning_effort": effort}, {}


cerebras = _CerebrasProfile(
    name="cerebras",
    env_vars=("CEREBRAS_API_KEY",),
    display_name="Cerebras",
    description="Cerebras — very fast, strict request schema",
    signup_url="https://cloud.cerebras.ai",
    base_url="https://api.cerebras.ai/v1",
    fallback_models=(
        "zai-glm-4.7",
        "gpt-oss-120b",
        "gemma-4-31b",
    ),
    default_max_tokens=8192,
)

register_provider(cerebras)
