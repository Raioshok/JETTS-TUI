"""Cerebras provider profile.

Strict schema: unknown body fields are a 400, and max_tokens is INVALID (use max_completion_tokens).

Endpoint, model ids and quirks verified against the live API.
"""

from providers import register_provider
from providers.base import ProviderProfile


class _CerebrasProfile(ProviderProfile):
    def build_reasoning_kwargs(self, *, reasoning_config=None, **context):
        """Map JettsTUI's reasoning intent onto what this provider accepts.

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
    # Verified 2026-09-23 against Cerebras' live public catalogue
    # (https://api.cerebras.ai/public/v1/models, no key required), which serves
    # exactly two models: it carries neither `zai-glm-4.7` nor `gemma-4-31b`.
    # Both were phantom fallbacks; `qwen-3.8-27b` is added as the second real id.
    fallback_models=(
        "gpt-oss-120b",
        "qwen-3.8-27b",
    ),
    default_max_tokens=8192,
)

register_provider(cerebras)
