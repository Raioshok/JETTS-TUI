"""NVIDIA NIM provider profile."""

from providers import register_provider
from providers.base import ProviderProfile

nvidia = ProviderProfile(
    name="nvidia",
    aliases=("nvidia-nim",),
    env_vars=("NVIDIA_API_KEY",),
    display_name="NVIDIA NIM",
    description="NVIDIA NIM — accelerated inference",
    signup_url="https://build.nvidia.com/",
    # Exercised with real tool-calling requests, not read off GET /v1/models:
    # kimi-k2.6 is listed there but 404s on chat/completions ("Function ...
    # Not found for account"), and qwen3-coder-480b is 410 Gone. Ordered by
    # measured latency.
    #
    # Re-probed 2026-09-23 (real chat/completions call per model): every entry
    # previously listed here — glm-5.2, deepseek-v4-flash, minimax-m3,
    # deepseek-v4-pro, gpt-oss-120b, llama-3.3-70b-instruct — returned
    # HTTP 410 "has reached its end of life". The whole curated list had
    # rotted while GET /v1/models kept advertising 82 models (most of which
    # 404 on chat). These five are the ones that actually answered.
    fallback_models=(
        "nvidia/nemotron-3-super-120b-a12b",
        "nvidia/nemotron-3.5-lightning-30b-a3b",
        "openai/gpt-oss-20b",
        "meta/muse-glimmer-30b",
        "z-ai/glm-5.3",
    ),
    base_url="https://integrate.api.nvidia.com/v1",
    default_max_tokens=16384,
)

register_provider(nvidia)
