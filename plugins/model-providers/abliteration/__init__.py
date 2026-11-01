"""Abliteration provider profile.

OpenAI-compatible hosted API for abliterated (low-refusal) models, aimed at
security research, red teaming and training-data generation. Endpoint and
model ids taken from https://docs.abliteration.ai/models on 2026-11-01:

  - Base URL:  https://api.abliteration.ai/v1
  - Auth: Bearer token in the Authorization header, Chat Completions format.
  - Models: abliterated-model-large-v2 (1M ctx), abliterated-model-large-flash
    (1M ctx), abliterated-model (262K ctx). abliterated-model-large is
    deprecated and left out.
"""

from providers import register_provider
from providers.base import ProviderProfile


abliteration = ProviderProfile(
    name="abliteration",
    aliases=("abliteration-ai", "abliterated"),
    env_vars=("ABLITERATION_API_KEY", "ABLITERATION_BASE_URL"),
    display_name="Abliteration",
    description="Abliteration — low-refusal models for security research and red teaming",
    signup_url="https://abliteration.ai/",
    base_url="https://api.abliteration.ai/v1",
    fallback_models=(
        "abliterated-model-large-v2",
        "abliterated-model-large-flash",
        "abliterated-model",
    ),
)

register_provider(abliteration)
