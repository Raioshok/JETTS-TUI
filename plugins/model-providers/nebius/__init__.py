"""Nebius Token Factory provider profile.

Formerly Nebius AI Studio. Model ids are case-sensitive Vendor/Model form.

Endpoint, model ids and quirks verified against the live API.
"""

from providers import register_provider
from providers.base import ProviderProfile


class _NebiusProfile(ProviderProfile):
    def build_reasoning_kwargs(self, *, reasoning_config=None, **context):
        """Map FreeIDE's reasoning intent onto what this provider accepts.

        Returns ({api_kwargs}, {extra_body}). Emits nothing when the mapping is
        not certain — a wrong field is a hard 4xx on strict providers, not a
        degraded response.
        """
        if not reasoning_config:
            return {}, {}
        on = (reasoning_config.get("effort") or "medium") not in ("none", "off")
        return {}, {"chat_template_kwargs": {"enable_thinking": on}}


nebius = _NebiusProfile(
    name="nebius",
    env_vars=("NEBIUS_API_KEY",),
    display_name="Nebius Token Factory",
    description="Nebius — trial credits, hosts Qwen3-Coder-480B",
    signup_url="https://tokenfactory.nebius.com",
    base_url="https://api.tokenfactory.nebius.com/v1",
    fallback_models=(
        "Qwen/Qwen3-Coder-480B-A35B-Instruct",
        "deepseek-ai/DeepSeek-V3-0324",
        "openai/gpt-oss-120b",
    ),
    default_max_tokens=8192,
)

register_provider(nebius)
