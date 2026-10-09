"""Alibaba Cloud DashScope provider profile.

New Model Studio (Singapore) accounts get 1M input + 1M output tokens valid for
90 days, and each Qwen-Coder model carries its own 1M-token free quota.

Keys are REGION-SCOPED: an international key will not authenticate against the
Beijing host, which is the most common cause of a 401 here.
"""

from providers import register_provider
from providers.base import ProviderProfile


class _AlibabaProfile(ProviderProfile):
    def build_reasoning_kwargs(self, *, reasoning_config=None, **context):
        """Map a reasoning intent onto DashScope's thinking switch.

        DashScope takes ``enable_thinking`` at the ROOT of the request body —
        NOT nested inside ``chat_template_kwargs``, which is the vLLM/self-host
        convention and is silently ignored here. QwQ/QvQ are thinking-only and
        cannot be turned off at all.
        """
        if not reasoning_config:
            return {}, {}
        effort = reasoning_config.get("effort") or "medium"
        on = effort not in ("none", "off")
        extra: dict = {"enable_thinking": on}
        if on and effort == "high":
            extra["thinking_budget"] = 8192
        elif on and effort == "low":
            extra["thinking_budget"] = 1024
        return {}, extra


alibaba = _AlibabaProfile(
    name="alibaba",
    aliases=("dashscope", "alibaba-cloud", "qwen-dashscope"),
    env_vars=("DASHSCOPE_API_KEY",),
    display_name="Alibaba Qwen (Model Studio)",
    description="DashScope — 1M free tokens for 90 days, plus a free quota per Qwen-Coder model",
    signup_url="https://bailian.console.alibabacloud.com",
    base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    fallback_models=(
        "qwen3-coder-plus",
        "qwen3-coder-next",
        "qwen3.7-plus",
        "qwen3.6-flash",
        "qwen-max",
    ),
    default_max_tokens=8192,
)

register_provider(alibaba)
