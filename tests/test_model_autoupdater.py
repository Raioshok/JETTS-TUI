"""Tests for model autoupdater across OAuth and API key providers."""

from __future__ import annotations

import json
from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest
from jettstui.model_autoupdater import (
    format_update_report,
    get_autoupdate_status,
    get_updatable_providers,
    is_oauth_provider,
    maybe_auto_update_models,
    save_autoupdate_status,
    update_all_models,
    update_provider_models,
)


def test_is_oauth_provider():
    """is_oauth_provider recognizes known OAuth providers."""
    assert is_oauth_provider("antigravity") is True
    assert is_oauth_provider("openai-codex") is True
    assert is_oauth_provider("copilot") is True
    assert is_oauth_provider("xai-oauth") is True
    assert is_oauth_provider("qwen-oauth") is True
    assert is_oauth_provider("minimax-oauth") is True
    assert is_oauth_provider("openai-api") is False
    assert is_oauth_provider("deepseek") is False
    assert is_oauth_provider("openrouter") is False


def test_save_and_get_autoupdate_status(tmp_path, monkeypatch):
    """Status metadata is persisted and reloaded correctly."""
    status_file = tmp_path / "model_autoupdate_status.json"
    monkeypatch.setattr(
        "jettstui.model_autoupdater.get_autoupdate_status_path",
        lambda: status_file,
    )

    assert get_autoupdate_status() == {}

    data = {
        "timestamp": 123456789.0,
        "total_new_models": 3,
        "providers": {"antigravity": {"total": 14}},
    }
    save_autoupdate_status(data)

    loaded = get_autoupdate_status()
    assert loaded["timestamp"] == 123456789.0
    assert loaded["total_new_models"] == 3


def test_update_provider_models_detects_new_models(tmp_path, monkeypatch):
    """update_provider_models detects models added since previous cache."""
    # Previous cache had model-A only
    monkeypatch.setattr(
        "jettstui.models._load_provider_models_cache",
        lambda: {"testprov": {"models": ["model-A"]}},
    )

    # Live fetch returns model-A and model-B
    monkeypatch.setattr(
        "jettstui.models.cached_provider_model_ids",
        lambda prov, force_refresh=True: ["model-A", "model-B"],
    )

    res = update_provider_models("testprov", force_refresh=True)
    assert res["status"] == "updated"
    assert res["new_models"] == ["model-B"]
    assert res["total"] == 2
    assert res["error"] is None


def test_update_all_models_compiles_report(tmp_path, monkeypatch):
    """update_all_models runs parallel updates and persists summary."""
    status_file = tmp_path / "model_autoupdate_status.json"
    monkeypatch.setattr(
        "jettstui.model_autoupdater.get_autoupdate_status_path",
        lambda: status_file,
    )

    def fake_update(pid, force_refresh=True):
        return {
            "provider": pid,
            "kind": "oauth" if is_oauth_provider(pid) else "api_key",
            "status": "updated",
            "models": ["m1", "m2"],
            "new_models": ["m2"],
            "total": 2,
            "error": None,
        }

    monkeypatch.setattr(
        "jettstui.model_autoupdater.update_provider_models", fake_update
    )
    monkeypatch.setattr(
        "agent.models_dev.fetch_models_dev",
        lambda force_refresh=True: {"prov1": {"models": {"mod1": {}}}},
    )

    report = update_all_models(
        providers=["antigravity", "openai-api"],
        force_refresh=True,
        update_models_dev=True,
    )

    assert "antigravity" in report["providers"]
    assert "openai-api" in report["providers"]
    assert report["total_new_models"] == 2
    assert report["total_models"] == 4
    assert report["models_dev_count"] == 1
    assert status_file.exists()


def test_maybe_auto_update_models_interval_gating(tmp_path, monkeypatch):
    """maybe_auto_update_models triggers only when past interval."""
    # Mock fresh status (1 hour ago)
    import time
    now = time.time()
    monkeypatch.setattr(
        "jettstui.model_autoupdater.get_autoupdate_status",
        lambda: {"timestamp": now - 3600},  # 1 hour ago
    )
    monkeypatch.setattr(
        "jettstui.config.load_config",
        lambda: {"model_catalog": {"autoupdate": True, "autoupdate_interval_hours": 12}},
    )

    # 1 hour < 12 hours -> should not run
    assert maybe_auto_update_models(background=False) is False

    # Stale status (15 hours ago)
    monkeypatch.setattr(
        "jettstui.model_autoupdater.get_autoupdate_status",
        lambda: {"timestamp": now - (15 * 3600)},
    )
    monkeypatch.setattr(
        "jettstui.model_autoupdater.update_all_models",
        lambda **k: {"total_models": 10},
    )

    # Past 12 hours -> triggers update
    assert maybe_auto_update_models(background=False) is True


def test_format_update_report():
    """format_update_report prints clean summary of changes."""
    report = {
        "duration_seconds": 1.25,
        "total_new_models": 2,
        "models_dev_count": 4000,
        "providers": {
            "antigravity": {
                "kind": "oauth",
                "status": "updated",
                "total": 14,
                "new_models": ["gemini-3.5-pro", "gemini-3.5-flash"],
            },
            "deepseek": {
                "kind": "api_key",
                "status": "unchanged",
                "total": 3,
                "new_models": [],
            },
            "broken": {
                "kind": "api_key",
                "status": "error",
                "error": "Connection timed out",
                "total": 0,
                "new_models": [],
            },
        },
    }

    out = format_update_report(report, use_color=False)
    assert "antigravity [OAuth]: 14 models (+2 new: gemini-3.5-pro, gemini-3.5-flash)" in out
    assert "deepseek [API Key]: 3 models (up to date)" in out
    assert "broken [API Key]: error (Connection timed out)" in out
    assert "4000 models synced" in out
    assert "Completed in 1.25s · 2 new model(s) discovered." in out


def test_cmd_model_update_dispatches_cleanly(monkeypatch, capsys):
    """cmd_model with update action invokes autoupdater and prints report."""
    from jettstui.main import cmd_model

    fake_report = {
        "duration_seconds": 0.5,
        "total_new_models": 1,
        "models_dev_count": 0,
        "providers": {
            "openrouter": {
                "kind": "api_key",
                "status": "updated",
                "total": 5,
                "new_models": ["new-model-1"],
            }
        },
    }

    monkeypatch.setattr(
        "jettstui.model_autoupdater.update_all_models",
        lambda **k: fake_report,
    )

    args = Namespace(action="update", update=True, refresh=False)
    cmd_model(args)

    out = capsys.readouterr().out
    assert "Checking for newer models" in out
    assert "openrouter [API Key]: 5 models (+1 new: new-model-1)" in out


def test_antigravity_gemini_4_argon_detection():
    """Verify Gemini 4 Argon is detected and resolved for Antigravity OAuth."""
    from jettstui.antigravity_auth import DEFAULT_ANTIGRAVITY_MODELS, fetch_available_models
    from jettstui.models import _PROVIDER_MODELS
    from jettstui.model_switch import switch_model, _ensure_direct_aliases

    _ensure_direct_aliases()

    # 1. Present in default and static models
    assert "gemini-4-argon" in DEFAULT_ANTIGRAVITY_MODELS
    assert "gemini-4-argon" in _PROVIDER_MODELS["antigravity"]

    # 2. Returned in fetch_available_models discovery
    models = fetch_available_models("dummy-token", "dummy-project")
    assert "gemini-4-argon" in models

    # 3. Model switch aliases resolve cleanly to Antigravity
    for alias in ["argon", "4 argon", "4-argon", "gemini-4", "gemini-4-argon"]:
        res = switch_model(alias, current_provider="antigravity", current_model="gemini-3.8-flash-tiered")
        assert res.success is True, f"Failed for alias {alias}: {res.error_message}"
        assert res.target_provider == "antigravity"
        assert res.new_model == "gemini-4-argon"


def test_antigravity_opus_5_5_sonnet_5_5_and_model_cleanup():
    """Verify Opus 5.5 and Sonnet 5.5 are present and bloated models are discarded."""
    from jettstui.antigravity_auth import (
        DEFAULT_ANTIGRAVITY_MODELS,
        fetch_available_models,
        _is_antigravity_usable_model,
    )
    from jettstui.models import _PROVIDER_MODELS
    from jettstui.model_switch import switch_model, _ensure_direct_aliases

    _ensure_direct_aliases()

    # 1. New Opus 5.5 and Sonnet 5.5 models are present
    assert "claude-opus-5-5-thinking" in DEFAULT_ANTIGRAVITY_MODELS
    assert "claude-sonnet-5-5" in DEFAULT_ANTIGRAVITY_MODELS
    assert "claude-opus-5-5-thinking" in _PROVIDER_MODELS["antigravity"]
    assert "claude-sonnet-5-5" in _PROVIDER_MODELS["antigravity"]

    # 2. Obsolete / bloated models are discarded by cleanup filter
    assert not _is_antigravity_usable_model("gemini-2.5-flash")
    assert not _is_antigravity_usable_model("gemini-2.5-pro")
    assert not _is_antigravity_usable_model("chat_20706")
    assert not _is_antigravity_usable_model("tab_jump_flash_lite_preview")
    assert not _is_antigravity_usable_model("gemini-3.5-flash-extra-low")
    assert not _is_antigravity_usable_model("gemini-3.6-flash-low")
    assert not _is_antigravity_usable_model("gemini-3.7-flash-tiered")
    assert not _is_antigravity_usable_model("gemini-3-flash-agent")
    assert not _is_antigravity_usable_model("gpt-oss-120b-medium")

    # 3. Clean models are accepted
    assert _is_antigravity_usable_model("gemini-4-argon")
    assert _is_antigravity_usable_model("gemini-3.8-flash-tiered")
    assert _is_antigravity_usable_model("claude-opus-5-5-thinking")
    assert _is_antigravity_usable_model("claude-sonnet-5-5")

    # 4. Alias resolution for Opus 5.5 and Sonnet 5.5
    for alias, expected in [
        ("opus 5.5", "claude-opus-5-5-thinking"),
        ("opus", "claude-opus-5-5"),
        ("sonnet 5.5", "claude-sonnet-5-5"),
        ("sonnet", "claude-sonnet-5-5"),
    ]:
        res = switch_model(alias, current_provider="antigravity", current_model="gemini-3.8-flash-tiered")
        assert res.success is True, f"Failed for {alias}: {res.error_message}"
        assert res.target_provider == "antigravity"
        assert res.new_model == expected


