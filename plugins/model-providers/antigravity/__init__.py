"""Google Antigravity provider profile.

antigravity: Gemini + Claude through Google's Cloud Code backend, signed in
with a Google account (Google AI Pro / Ultra plan quota). Uses
AntigravityClient (agent/antigravity_adapter.py); auth lives in
jettstui/antigravity_auth.py.
"""

from typing import Any

from providers import register_provider
from providers.base import ProviderProfile

_CLAUDE_EFFORT_BUDGETS = {"minimal": 4096, "low": 8192, "medium": 16384, "high": 32768}


class AntigravityProfile(ProviderProfile):
    """Antigravity — translate reasoning_config to the native thinking_config."""

    def build_extra_body(
        self, *, session_id: str | None = None, **context: Any
    ) -> dict[str, Any]:
        from agent.transports.chat_completions import _build_gemini_thinking_config

        model = str(context.get("model") or "").lower()
        reasoning_config = context.get("reasoning_config")
        if "claude" in model:
            if "-thinking" not in model:
                return {}
            if isinstance(reasoning_config, dict) and (
                reasoning_config.get("enabled") is False
                or str(reasoning_config.get("effort") or "").lower() == "none"
            ):
                return {"thinking_config": {"includeThoughts": False}}
            effort = "high"
            if isinstance(reasoning_config, dict):
                effort = str(reasoning_config.get("effort") or "high").lower()
            budget = _CLAUDE_EFFORT_BUDGETS.get(effort, _CLAUDE_EFFORT_BUDGETS["high"])
            return {"thinking_config": {"includeThoughts": True, "thinkingBudget": budget}}

        thinking_config = _build_gemini_thinking_config(model, reasoning_config)
        return {"thinking_config": thinking_config} if thinking_config else {}


antigravity = AntigravityProfile(
    name="antigravity",
    display_name="Google Antigravity",
    description="Google Antigravity (Google AI Pro / Ultra sign-in; Gemini 3 + Claude)",
    signup_url="https://antigravity.google/",
    aliases=(
        "google-antigravity",
        "antigravity-oauth",
        "google-ai-pro",
        "google-ai-ultra",
    ),
    api_mode="chat_completions",
    base_url="https://daily-cloudcode-pa.sandbox.googleapis.com",
    auth_type="oauth_external",
    supports_health_check=False,
    supports_vision=True,
    fallback_models=(
        "gemini-3.1-pro-high",
        "gemini-3.1-pro-low",
        "gemini-3-pro-high",
        "gemini-3-pro-low",
        "gemini-3-flash",
        "claude-opus-4-6-thinking",
        "claude-sonnet-4-6",
    ),
    default_aux_model="gemini-3-flash",
)

register_provider(antigravity)
