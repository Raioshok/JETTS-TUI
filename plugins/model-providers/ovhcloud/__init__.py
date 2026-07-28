"""OVHcloud AI Endpoints provider profile.

Anonymous access works ONLY with no Authorization header — a placeholder key returns 403. Ids are case- and separator-sensitive.

Endpoint, model ids and quirks verified against the live API.
"""

from providers import register_provider
from providers.base import ProviderProfile


class _OvhcloudProfile(ProviderProfile):
    def build_reasoning_kwargs(self, *, reasoning_config=None, **context):
        """Map FreeIDE's reasoning intent onto what this provider accepts.

        Returns ({api_kwargs}, {extra_body}). Emits nothing when the mapping is
        not certain — a wrong field is a hard 4xx on strict providers, not a
        degraded response.
        """
        return {}, {}


ovhcloud = _OvhcloudProfile(
    name="ovhcloud",
    env_vars=("OVH_AI_ENDPOINTS_ACCESS_TOKEN",),
    display_name="OVHcloud AI Endpoints",
    description="OVHcloud — EU-hosted, usable with no signup",
    signup_url="https://endpoints.ai.cloud.ovh.net",
    base_url="https://oai.endpoints.kepler.ai.cloud.ovh.net/v1",
    fallback_models=(
        "Qwen3-Coder-30B-A3B-Instruct",
        "Qwen3.5-397B-A17B",
        "gpt-oss-120b",
        "Meta-Llama-3_3-70B-Instruct",
    ),
    default_max_tokens=8192,
)

register_provider(ovhcloud)
