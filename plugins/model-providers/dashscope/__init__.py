"""Alibaba Qwen (Model Studio) provider profile.

Keys are region-scoped: an international key will not work against the Beijing host.

Endpoint, model ids and quirks verified against the live API.
"""

from providers import register_provider
from providers.base import ProviderProfile


class _DashscopeProfile(ProviderProfile):
    def build_reasoning_kwargs(self, *, reasoning_config=None, **context):
        """Map FreeIDE's reasoning intent onto what this provider accepts.

        Returns ({api_kwargs}, {extra_body}). Emits nothing when the mapping is
        not certain — a wrong field is a hard 4xx on strict providers, not a
        degraded response.
        """
        if not reasoning_config:
            return {}, {}
        on = (reasoning_config.get("effort") or "medium") not in ("none", "off")
        return {}, {"enable_thinking": on}


dashscope = _DashscopeProfile(
    name="dashscope",
    env_vars=("DASHSCOPE_API_KEY",),
    display_name="Alibaba Qwen (Model Studio)",
    description="DashScope — 1M free tokens for 90 days",
    signup_url="https://bailian.console.alibabacloud.com",
    base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    fallback_models=(
        "qwen3-coder-plus",
        "qwen3-coder-next",
        "qwen3.7-plus",
        "qwen-max",
    ),
    default_max_tokens=8192,
)

register_provider(dashscope)
