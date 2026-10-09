"""LLM7.io provider profile.

Turbo-tier models need no key. Usage arrives on the final content chunk, not a separate usage chunk.

Endpoint, model ids and quirks verified against the live API.
"""

from providers import register_provider
from providers.base import ProviderProfile


class _Llm7Profile(ProviderProfile):
    def build_reasoning_kwargs(self, *, reasoning_config=None, **context):
        """Map JettsTUI's reasoning intent onto what this provider accepts.

        Returns ({api_kwargs}, {extra_body}). Emits nothing when the mapping is
        not certain — a wrong field is a hard 4xx on strict providers, not a
        degraded response.
        """
        return {}, {}


llm7 = _Llm7Profile(
    name="llm7",
    env_vars=("LLM7_API_KEY",),
    display_name="LLM7.io",
    description="LLM7 — no signup for the turbo tier",
    signup_url="https://token.llm7.io",
    base_url="https://api.llm7.io/v1",
    fallback_models=(
        "codestral-latest",
        "gpt-oss:20b",
        "gemini-3.1-flash-lite",
        "minimax-m2.7",
    ),
    default_max_tokens=4096,
)

register_provider(llm7)
