"""Tests for the Nous-FreeIDE-3/4 non-agentic warning detector.

Prior to this check, the warning fired on any model whose name contained
``"freeide"`` anywhere (case-insensitive). That false-positived on unrelated
local Modelfiles such as ``freeide-brain:qwen3-14b-ctx16k`` — a tool-capable
Qwen3 wrapper that happens to live under the "freeide" tag namespace.

``is_nous_freeide_non_agentic`` should only match the actual Nous Research
FreeIDE-3 / FreeIDE-4 chat family.
"""

from __future__ import annotations

import pytest

from freeide_cli.model_switch import (
    _FREEIDE_MODEL_WARNING,
    _check_freeide_model_warning,
    is_nous_freeide_non_agentic,
)


@pytest.mark.parametrize(
    "model_name",
    [
        "NousResearch/FreeIDE-3-Llama-3.1-70B",
        "NousResearch/FreeIDE-3-Llama-3.1-405B",
        "freeide-3",
        "FreeIDE-3",
        "freeide-4",
        "freeide-4-405b",
        "freeide_4_70b",
        "openrouter/freeide3:70b",
        "openrouter/nousresearch/freeide-4-405b",
        "NousResearch/FreeIDE3",
        "freeide-3.1",
    ],
)
def test_matches_real_nous_freeide_chat_models(model_name: str) -> None:
    assert is_nous_freeide_non_agentic(model_name), (
        f"expected {model_name!r} to be flagged as Nous FreeIDE 3/4"
    )
    assert _check_freeide_model_warning(model_name) == _FREEIDE_MODEL_WARNING


@pytest.mark.parametrize(
    "model_name",
    [
        # Kyle's local Modelfile — qwen3:14b under a custom tag
        "freeide-brain:qwen3-14b-ctx16k",
        "freeide-brain:qwen3-14b-ctx32k",
        "freeide-honcho:qwen3-8b-ctx8k",
        # Plain unrelated models
        "qwen3:14b",
        "qwen3-coder:30b",
        "qwen2.5:14b",
        "claude-opus-4-6",
        "anthropic/claude-sonnet-4.5",
        "gpt-5",
        "openai/gpt-4o",
        "google/gemini-2.5-flash",
        "deepseek-chat",
        # Non-chat FreeIDE models we don't warn about
        "freeide-llm-2",
        "freeide2-pro",
        "nous-freeide-2-mistral",
        # Edge cases
        "",
        "freeide",  # bare "freeide" isn't the 3/4 family
        "freeide-brain",
        "brain-freeide-3-impostor",  # "3" not preceded by /: boundary
    ],
)
def test_does_not_match_unrelated_models(model_name: str) -> None:
    assert not is_nous_freeide_non_agentic(model_name), (
        f"expected {model_name!r} NOT to be flagged as Nous FreeIDE 3/4"
    )
    assert _check_freeide_model_warning(model_name) == ""


def test_none_like_inputs_are_safe() -> None:
    assert is_nous_freeide_non_agentic("") is False
    # Defensive: the helper shouldn't crash on None-ish falsy input either.
    assert _check_freeide_model_warning("") == ""
