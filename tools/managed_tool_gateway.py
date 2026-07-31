"""Managed-tool gateway stubs.

The hosted managed-tool gateway (a remote vendor passthrough) has been
removed. These stubs remain only so callers that still probe for a managed
backend resolve to "unavailable" and fall back to direct/local execution.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def resolve_managed_tool_gateway(
    vendor: str,
    gateway_builder: Optional[Callable[[str], str]] = None,
    token_reader: Optional[Callable[[], Optional[str]]] = None,
):
    """The managed-tool gateway has been removed; no managed backend exists."""
    return None


def is_managed_tool_gateway_ready(
    vendor: str,
    gateway_builder: Optional[Callable[[str], str]] = None,
    token_reader: Optional[Callable[[], Optional[str]]] = None,
) -> bool:
    """The managed-tool gateway has been removed; it is never ready."""
    return False
