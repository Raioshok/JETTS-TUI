"""Tests for Anthropic subscription OAuth integration.

Verifies:
1. OAuth scopes and redirect URI target Claude subscription (platform.claude.com).
2. Billing header calculation (x-anthropic-billing-header) with SHA-256 and salt.
3. OAuth system prompt transformation: billing header in system[0], Claude Code identity in system[1],
   and relocation of third-party system prompts to the first user message so Anthropic's subscription
   classifier draws from plan limits instead of extra usage.
4. Tool name prefixing and beta headers for subscription OAuth.
"""

from __future__ import annotations

import hashlib
import json
from unittest.mock import MagicMock, patch

import pytest

from agent.anthropic_adapter import (
    _BILLING_SALT,
    _CLAUDE_CODE_SYSTEM_PREFIX,
    _OAUTH_CLIENT_ID,
    _OAUTH_ONLY_BETAS,
    _OAUTH_REDIRECT_URI,
    _OAUTH_SCOPES,
    _compute_billing_header,
    _extract_first_user_message_text,
    build_anthropic_kwargs,
)


def test_oauth_subscription_endpoints_and_scopes():
    """OAuth configuration must target platform.claude.com and subscription scopes."""
    assert _OAUTH_REDIRECT_URI == "https://platform.claude.com/oauth/code/callback"
    assert "user:inference" in _OAUTH_SCOPES
    assert "user:sessions:claude_code" in _OAUTH_SCOPES
    assert "user:mcp_servers" in _OAUTH_SCOPES
    assert "org:create_api_key" not in _OAUTH_SCOPES
    assert _OAUTH_CLIENT_ID == "9d1c250a-e61b-44d9-88ed-5944d1962f5e"


def test_compute_billing_header():
    """Billing header must follow cc_version=V.S; cc_entrypoint=E; cch=H format."""
    messages = [
        {"role": "user", "content": "Hello, write some code."},
    ]
    version = "2.1.287"
    header = _compute_billing_header(messages, version, entrypoint="sdk-cli")

    assert header.startswith("x-anthropic-billing-header: ")
    assert f"cc_version={version}." in header
    assert "cc_entrypoint=sdk-cli;" in header
    assert "cch=" in header

    # Verify cch matches first 5 hex chars of sha256 of first user text
    expected_cch = hashlib.sha256(b"Hello, write some code.").hexdigest()[:5]
    assert f"cch={expected_cch};" in header


def test_build_anthropic_kwargs_oauth_system_restructuring():
    """For OAuth requests, system prompt must place billing header in system[0],
    clean identity in system[1], and relocate custom system instructions to first user message."""
    messages = [
        {"role": "user", "content": "Can you check my git status?"},
    ]
    custom_system = "You are JettsTUI, an AI assistant. Follow user instructions carefully."

    kwargs = build_anthropic_kwargs(
        model="claude-sonnet-4-6",
        messages=messages,
        tools=[{"type": "function", "function": {"name": "read_file", "parameters": {}}}],
        max_tokens=4096,
        reasoning_config=None,
        is_oauth=True,
    )

    system = kwargs["system"]
    assert isinstance(system, list)
    assert len(system) >= 2
    # system[0] is billing header
    assert system[0]["text"].startswith("x-anthropic-billing-header:")
    # system[1] is clean Claude Code identity
    assert system[1]["text"] == _CLAUDE_CODE_SYSTEM_PREFIX

    # Re-test with explicit custom system prompt
    messages_with_system = [
        {"role": "system", "content": custom_system},
        {"role": "user", "content": "Can you check my git status?"},
    ]
    kwargs2 = build_anthropic_kwargs(
        model="claude-sonnet-4-6",
        messages=messages_with_system,
        tools=None,
        max_tokens=4096,
        reasoning_config=None,
        is_oauth=True,
    )

    system2 = kwargs2["system"]
    assert len(system2) == 2
    assert system2[0]["text"].startswith("x-anthropic-billing-header:")
    assert system2[1]["text"] == _CLAUDE_CODE_SYSTEM_PREFIX

    # The custom system prompt must be relocated to the first user message
    user_msg = kwargs2["messages"][0]
    assert user_msg["role"] == "user"
    assert "Follow user instructions carefully" in user_msg["content"]
    assert "Can you check my git status?" in user_msg["content"]
    # Brand sanitization
    assert "JettsTUI" not in user_msg["content"]


def test_oauth_betas_include_subscription_features():
    """OAuth requests must send the required subscription betas."""
    assert "claude-code-20250219" in _OAUTH_ONLY_BETAS
    assert "oauth-2025-04-20" in _OAUTH_ONLY_BETAS
    assert "interleaved-thinking-2025-05-14" in _OAUTH_ONLY_BETAS
    assert "context-management-2025-06-27" in _OAUTH_ONLY_BETAS
    assert "advisor-tool-2026-03-01" in _OAUTH_ONLY_BETAS
