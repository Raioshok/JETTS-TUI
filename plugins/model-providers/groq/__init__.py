"""Groq provider profile.

Rejects logprobs / logit_bias / top_logprobs / messages[].name with a 400.

Endpoint, model ids and quirks verified against the live API.
"""

from providers import register_provider
from providers.base import ProviderProfile


class _GroqProfile(ProviderProfile):
    def build_reasoning_kwargs(self, *, reasoning_config=None, **context):
        """Map JettsTUI's reasoning intent onto what this provider accepts.

        Returns ({api_kwargs}, {extra_body}). Emits nothing when the mapping is
        not certain — a wrong field is a hard 4xx on strict providers, not a
        degraded response.
        """
        model_id = (context.get("model") or "").lower()
        if not reasoning_config:
            return {}, {}
        effort = reasoning_config.get("effort")
        if "gpt-oss" in model_id:
            if effort in ("low", "medium", "high"):
                return {"reasoning_effort": effort}, {}
            return {"reasoning_effort": "low"}, {}
        if "qwen" in model_id:
            return {"reasoning_effort": "none" if effort in ("none", "off") else "default"}, {}
        return {}, {}


groq = _GroqProfile(
    name="groq",
    env_vars=("GROQ_API_KEY",),
    display_name="Groq",
    description="Groq — fastest free tier",
    signup_url="https://console.groq.com/keys",
    base_url="https://api.groq.com/openai/v1",
    fallback_models=(
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "qwen/qwen3.6-27b",
        "minimaxai/minimax-m2.7",
        "llama-3.3-70b-versatile",
    ),
    default_max_tokens=8192,
)

register_provider(groq)
