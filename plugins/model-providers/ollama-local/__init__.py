"""Ollama (local) provider profile.

Needs `ollama serve` running. Your real model list is whatever you have pulled.

Endpoint, model ids and quirks verified against the live API.
"""

from providers import register_provider
from providers.base import ProviderProfile


class _Ollama_localProfile(ProviderProfile):
    def build_reasoning_kwargs(self, *, reasoning_config=None, **context):
        """Map FreeIDE's reasoning intent onto what this provider accepts.

        Returns ({api_kwargs}, {extra_body}). Emits nothing when the mapping is
        not certain — a wrong field is a hard 4xx on strict providers, not a
        degraded response.
        """
        if not reasoning_config:
            return {}, {}
        effort = reasoning_config.get("effort") or "medium"
        if effort in ("none", "off"):
            return {}, {}
        return {"reasoning_effort": effort}, {}


ollama_local = _Ollama_localProfile(
    name="ollama-local",
    env_vars=("OLLAMA_API_KEY", "OLLAMA_LOCAL_BASE_URL"),
    display_name="Ollama (local)",
    description="Ollama — runs entirely on your machine",
    signup_url="https://ollama.com/download",
    base_url="http://localhost:11434/v1",
    fallback_models=(
        "qwen3-coder:30b",
        "qwen2.5-coder:7b",
        "gpt-oss:20b",
        "devstral",
    ),
    default_max_tokens=4096,
)

register_provider(ollama_local)
