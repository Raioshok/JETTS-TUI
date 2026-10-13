"""Dahl Inference provider profile.

OpenAI-compatible open-model inference API backed by a decentralized GPU
network (Gonka). Endpoint, model ids and catalog verified against the live
API on 2026-10-13:

  - Base URL:  https://inference.dahl.global/v1
  - /v1/models is public (no auth required) and serves exactly three ids
    owned by "gonka": MiniMaxAI/MiniMax-M2.7, zai-org/GLM-5.3-Flash,
    deepseek-ai/DeepSeek-V4-Flash-0731 (Qwen 3.8 Flash listed "coming soon").
  - Auth: Bearer token in the Authorization header, Chat Completions format.
"""

from providers import register_provider
from providers.base import ProviderProfile


dahl = ProviderProfile(
    name="dahl",
    aliases=("dahl-inference", "dahl-ai"),
    env_vars=("DAHL_API_KEY", "DAHL_BASE_URL"),
    display_name="Dahl Inference",
    description="Dahl — open models (MiniMax M2.7, GLM 5.3 Flash, DeepSeek V4 Flash) on a decentralized GPU network",
    signup_url="https://inference.dahl.global/",
    base_url="https://inference.dahl.global/v1",
    # Verified 2026-10-13 against the live public catalogue
    # (https://inference.dahl.global/v1/models, no key required).
    fallback_models=(
        "MiniMaxAI/MiniMax-M2.7",
        "zai-org/GLM-5.3-Flash",
        "deepseek-ai/DeepSeek-V4-Flash-0731",
    ),
    default_max_tokens=8192,
)

register_provider(dahl)