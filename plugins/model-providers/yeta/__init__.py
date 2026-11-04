"""Yeta Platform provider profile.

OpenAI-compatible inference API for leading AI models and video generation.
Endpoint, model ids and catalog verified against the live API on 2026-11-04:

  - Base URL: https://platform.yeta.ai/v1
  - Models endpoint: https://platform.yeta.ai/v1/models (requires Bearer auth)
  - Public pricing endpoint: https://platform.yeta.ai/api/pricing
  - Live chat models: deepseek-v4.1-flash, deepseek-v4.1-flash-uncensored, glm-5.3-flash
  - Video models: koray-1.0, wan-3.0-uncensored, seedance-2.0-fast, seedance-2.0-pro, etc.
  - Auth: Bearer token in Authorization header, Chat Completions format.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from jettstui import __version__ as _JETTSTUI_VERSION
from providers import register_provider
from providers.base import ProviderProfile, _profile_user_agent


class YetaProfile(ProviderProfile):
    """Yeta Platform provider profile."""

    def fetch_models(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 8.0,
    ) -> list[str] | None:
        """Fetch the live model list from Yeta Platform.

        Uses the authenticated /v1/models endpoint when an API key is provided,
        and falls back to the public /api/pricing catalog when unauthenticated.
        """
        if api_key:
            models = super().fetch_models(
                api_key=api_key,
                base_url=base_url,
                timeout=timeout,
            )
            if models:
                return models

        # Keyless fallback: discover from public pricing catalog
        try:
            from jettstui.urllib_security import open_credentialed_url

            req = urllib.request.Request("https://platform.yeta.ai/api/pricing")
            req.add_header("Accept", "application/json")
            req.add_header("User-Agent", _profile_user_agent())
            with open_credentialed_url(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode())
            items = data.get("data", [])
            discovered: list[str] = []
            for item in items:
                if isinstance(item, dict):
                    name = item.get("model_name")
                    if name and name not in discovered:
                        discovered.append(name)
            return discovered or None
        except Exception:
            return None


yeta = YetaProfile(
    name="yeta",
    aliases=("yeta-platform", "yeta-ai", "yetaai"),
    display_name="Yeta Platform",
    description="Yeta Platform — OpenAI-compatible API for frontier models and video generation",
    signup_url="https://platform.yeta.ai/",
    env_vars=("YETA_API_KEY", "YETA_BASE_URL"),
    base_url="https://platform.yeta.ai/v1",
    auth_type="api_key",
    default_headers={"User-Agent": f"JettsTUIAgent/{_JETTSTUI_VERSION}"},
    default_aux_model="deepseek-v4.1-flash",
    # Live-verified on 2026-11-04 from https://platform.yeta.ai/api/pricing
    fallback_models=(
        "deepseek-v4.1-flash",
        "deepseek-v4.1-flash-uncensored",
        "glm-5.3-flash",
    ),
    default_max_tokens=8192,
)

register_provider(yeta)
