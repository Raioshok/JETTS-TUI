"""Freebuff model provider profile.

Freebuff (freebuff.com / codebuff.com) provides 1-hour free model sessions
funded by promotional capacity and ads across DeepSeek, OpenAI, Google,
MiniMax, Anthropic, and Qwen models.
"""

from __future__ import annotations

import logging
from typing import Any

from providers import register_provider
from providers.base import ProviderProfile

logger = logging.getLogger(__name__)

# Fallback models verified from the Freebuff CLI release binary (v0.2.29, Oct 2026).
_FREEBUFF_FALLBACK_MODELS = (
    "deepseek/deepseek-v4-pro",
    "deepseek/deepseek-v4.1-flash",
    "openai/gpt-5.6-luna",
    "openai/gpt-6-luna",
    "openai/gpt-6.1-sol",
    "google/gemini-4-argon",
    "google/gemini-3.8-flash",
    "minimax/minimax-m3",
    "anthropic/claude-opus-5.5",
    "anthropic/claude-sonnet-5",
    "qwen/qwen3.8-max-prime",
)


class FreebuffProfile(ProviderProfile):
    """Freebuff — OpenAI chat completions format with 1h free session admission."""

    def prepare_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalize messages for Freebuff chat completions."""
        return messages

    def build_extra_body(
        self, *, session_id: str | None = None, **context: Any
    ) -> dict[str, Any]:
        """Freebuff extra body parameters."""
        return {}

    def build_api_kwargs_extras(
        self,
        *,
        reasoning_config: dict | None = None,
        **context: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Freebuff reasoning controls."""
        extra_body: dict[str, Any] = {}
        top_level: dict[str, Any] = {}

        if reasoning_config and isinstance(reasoning_config, dict):
            effort = (reasoning_config.get("effort") or "").strip().lower()
            if effort in {"low", "medium", "high"}:
                top_level["reasoning_effort"] = effort

        return extra_body, top_level

    def ensure_admission(self, auth_token: str, model: str) -> dict[str, Any]:
        """Ensure a 1-hour free session is admitted on Freebuff for the model."""
        from jettstui.freebuff_auth import get_or_create_freebuff_session

        return get_or_create_freebuff_session(auth_token, model)


freebuff = FreebuffProfile(
    name="freebuff",
    aliases=("freebuff-oauth", "freebuff-ai", "codebuff"),
    display_name="Freebuff",
    description="Freebuff (free coding agent models with 1h sessions, freebuff.com)",
    signup_url="https://freebuff.com",
    env_vars=("FREEBUFF_API_KEY", "FREEBUFF_BASE_URL"),
    base_url="https://codebuff.com/api/v1",
    auth_type="oauth_external",
    default_headers={"x-freebuff-sse-gzip-recovery": "1"},
    default_max_tokens=32768,
    supports_vision=True,
    fallback_models=_FREEBUFF_FALLBACK_MODELS,
)

register_provider(freebuff)
