"""Built-in keyless web search + extract plugin — bundled, auto-loaded.

DuckDuckGo HTML search and direct page fetching over ``httpx`` with a stdlib
HTML→Markdown converter. Needs no API key and no optional package, so
``web_search`` and ``web_extract`` work on a fresh install.
"""

from __future__ import annotations

from plugins.web.native.provider import NativeWebSearchProvider


def register(ctx) -> None:
    """Register the built-in provider with the plugin context."""
    ctx.register_web_search_provider(NativeWebSearchProvider())
