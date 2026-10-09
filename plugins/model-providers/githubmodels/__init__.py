"""GitHub Models provider profile.

Base URL has NO /v1. Every tier is capped at 8000 input / 4000 output tokens per request.

Endpoint, model ids and quirks verified against the live API.
"""

from providers import register_provider
from providers.base import ProviderProfile


class _GithubmodelsProfile(ProviderProfile):
    def build_reasoning_kwargs(self, *, reasoning_config=None, **context):
        """Map JettsTUI's reasoning intent onto what this provider accepts.

        Returns ({api_kwargs}, {extra_body}). Emits nothing when the mapping is
        not certain — a wrong field is a hard 4xx on strict providers, not a
        degraded response.
        """
        return {}, {}


githubmodels = _GithubmodelsProfile(
    name="githubmodels",
    env_vars=("GITHUB_MODELS_TOKEN", "GITHUB_TOKEN"),
    display_name="GitHub Models",
    description="GitHub Models — uses a PAT with models:read",
    signup_url="https://github.com/settings/tokens",
    base_url="https://models.github.ai/inference",
    fallback_models=(
        "openai/gpt-4.1",
        "openai/gpt-4.1-mini",
        "openai/o4-mini",
        "deepseek/deepseek-v3-0324",
    ),
    default_headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2026-03-10"},
    default_max_tokens=4000,
)

register_provider(githubmodels)
