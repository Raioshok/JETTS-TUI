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
    # kimi-k2.6 is listed there but 404s on chat/completions, and
    # qwen3-coder-480b is 410 Gone. Ordered by measured latency.
    fallback_models=(
        "z-ai/glm-5.2",
        "deepseek-ai/deepseek-v4-flash",
        "minimaxai/minimax-m3",
        "deepseek-ai/deepseek-v4-pro",
        "openai/gpt-oss-120b",
        "meta/llama-3.3-70b-instruct",
    ),
    base_url="https://integrate.api.nvidia.com/v1",
    default_max_tokens=16384,
)

register_provider(nvidia)
