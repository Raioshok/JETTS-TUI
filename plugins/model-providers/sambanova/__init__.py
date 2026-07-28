"""SambaNova provider profile.

Model ids are CASE-SENSITIVE and mixed-case — never lowercase them.

Endpoint, model ids and quirks verified against the live API.
"""

from providers import register_provider
from providers.base import ProviderProfile


class _SambanovaProfile(ProviderProfile):
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


sambanova = _SambanovaProfile(
    name="sambanova",
    env_vars=("SAMBANOVA_API_KEY",),
    display_name="SambaNova",
    description="SambaNova — fast free tier",
    signup_url="https://cloud.sambanova.ai",
    base_url="https://api.sambanova.ai/v1",
    fallback_models=(
        "DeepSeek-V3.1",
        "MiniMax-M2.7",
        "Meta-Llama-3.3-70B-Instruct",
        "gpt-oss-120b",
    ),
    default_max_tokens=8192,
)

register_provider(sambanova)
