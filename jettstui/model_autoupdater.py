"""Model autoupdater — automatically discovers and updates models across providers.

Fetches the newest models for:
  1. OAuth-backed providers (OpenAI Codex, Google Antigravity, GitHub Copilot,
     xAI Grok OAuth, Qwen Portal OAuth, MiniMax OAuth) using active session tokens.
  2. API-key providers (OpenAI, Anthropic, Gemini, DeepSeek, Z.AI, Kimi, StepFun,
     Dahl, Groq, Mistral, Alibaba, HuggingFace, etc.) using configured credentials.
  3. The models.dev community registry (covering 4000+ models across 109+ providers).

Features:
  - Parallel background updates (ThreadPoolExecutor) — non-blocking, finishes in ~1-2s.
  - Auto-updates on startup / periodic timer if stale (> 12h by default).
  - Persists to $JETTSTUI_HOME/provider_models_cache.json and status metadata.
  - Detects and highlights newly released models (+N new).
  - CLI subcommand: `jettstui model update` (or `jettstui model --update`).
  - Slash command: `/model update`.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from jettstui_constants import get_jettstui_home
from utils import atomic_json_write

logger = logging.getLogger(__name__)

# Known OAuth providers supported in JettsTUI
OAUTH_PROVIDERS: tuple[str, ...] = (
    "openai-codex",
    "antigravity",
    "copilot",
    "copilot-acp",
    "xai-oauth",
    "qwen-oauth",
    "minimax-oauth",
)

# Concurrency lock to prevent overlapping background update runs
_UPDATE_LOCK = threading.Lock()
_IS_UPDATING = False


def get_autoupdate_status_path() -> Path:
    """Return path to model autoupdate status metadata."""
    return get_jettstui_home() / "model_autoupdate_status.json"


def get_autoupdate_status() -> dict[str, Any]:
    """Load current model autoupdate status, or return empty default."""
    path = get_autoupdate_status_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.debug("Failed to read model autoupdate status: %s", exc)
        return {}


def save_autoupdate_status(status: dict[str, Any]) -> None:
    """Persist model autoupdate status metadata."""
    path = get_autoupdate_status_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json_write(path, status, indent=2)
    except Exception as exc:
        logger.debug("Failed to save model autoupdate status: %s", exc)


def is_oauth_provider(provider_id: str) -> bool:
    """Return True if provider_id is a known OAuth-based provider."""
    from jettstui.models import normalize_provider

    normalized = normalize_provider(provider_id)
    return normalized in OAUTH_PROVIDERS


def get_updatable_providers() -> list[str]:
    """Return list of providers that have valid credentials or are configured.

    Includes:
      - Active/configured OAuth providers with saved session tokens
      - API-key providers with set environment keys or saved config
      - OpenRouter (always checkable)
    """
    from jettstui.auth import PROVIDER_REGISTRY, is_provider_explicitly_configured
    from jettstui.models import normalize_provider

    updatable: set[str] = set()

    # 1. OAuth providers with credentials or explicit configuration
    for oauth_pid in OAUTH_PROVIDERS:
        norm = normalize_provider(oauth_pid)
        if is_provider_explicitly_configured(oauth_pid) or is_provider_explicitly_configured(norm):
            updatable.add(norm)

    # 2. API key providers in registry
    for pid in PROVIDER_REGISTRY:
        norm = normalize_provider(pid)
        if norm in OAUTH_PROVIDERS:
            continue
        if is_provider_explicitly_configured(pid) or is_provider_explicitly_configured(norm):
            updatable.add(norm)

    # 3. Always include OpenRouter if configured or if API key exists
    if os.getenv("OPENROUTER_API_KEY"):
        updatable.add("openrouter")

    # If nothing configured yet, at least check active provider or openrouter
    if not updatable:
        try:
            from jettstui.auth import get_active_provider

            active = get_active_provider()
            if active:
                updatable.add(normalize_provider(active))
        except Exception:
            pass

    return sorted(updatable)


def update_provider_models(
    provider_id: str,
    *,
    force_refresh: bool = True,
) -> dict[str, Any]:
    """Fetch live models for a single provider and detect new models.

    Returns dict:
      {
        "provider": str,
        "kind": "oauth" | "api_key",
        "status": "updated" | "unchanged" | "error",
        "models": list[str],
        "new_models": list[str],
        "total": int,
        "error": str | None,
      }
    """
    from jettstui.models import (
        _load_provider_models_cache,
        cached_provider_model_ids,
        normalize_provider,
    )

    norm = normalize_provider(provider_id)
    kind = "oauth" if norm in OAUTH_PROVIDERS else "api_key"

    # Get previously cached models to detect additions
    cache = _load_provider_models_cache()
    old_models: list[str] = []
    if isinstance(cache.get(norm), dict):
        old_models = cache[norm].get("models") or []
    old_set = {m.strip().lower() for m in old_models if m}

    try:
        live = cached_provider_model_ids(norm, force_refresh=force_refresh)
        # With no previous snapshot there is nothing to diff against — a first
        # fetch would otherwise report the provider's whole catalog as "new".
        new_models = [m for m in live if m.strip().lower() not in old_set] if old_set else []

        status = "updated" if new_models else ("unchanged" if live else "empty")
        return {
            "provider": norm,
            "kind": kind,
            "status": status,
            "models": live,
            "new_models": new_models,
            "total": len(live),
            "error": None,
        }
    except Exception as exc:
        logger.debug("Model update failed for %s: %s", norm, exc)
        return {
            "provider": norm,
            "kind": kind,
            "status": "error",
            "models": old_models,
            "new_models": [],
            "total": len(old_models),
            "error": str(exc),
        }


def update_all_models(
    providers: Optional[list[str]] = None,
    *,
    force_refresh: bool = True,
    update_models_dev: bool = True,
    max_workers: int = 6,
    lock_already_held: bool = False,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Run parallel model updates across providers and the models.dev registry.

    Returns comprehensive report dict:
      {
        "timestamp": float,
        "iso_timestamp": str,
        "duration_seconds": float,
        "providers": {pid: result_dict, ...},
        "models_dev_count": int,
        "total_new_models": int,
        "total_models": int,
      }
    """
    global _IS_UPDATING
    if not lock_already_held:
        with _UPDATE_LOCK:
            if _IS_UPDATING:
                return {"error": "update already in progress"}
            _IS_UPDATING = True

    start_time = time.time()
    target_providers = providers if providers is not None else get_updatable_providers()
    provider_results: dict[str, dict[str, Any]] = {}
    models_dev_count = 0

    # Not a ``with`` block: its exit waits for every worker, so a hung provider
    # would hold the caller far past ``timeout``. Shut down without waiting.
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="model-update")
    try:
        future_to_pid = {
            executor.submit(
                update_provider_models, pid, force_refresh=force_refresh
            ): pid
            for pid in target_providers
        }

        # Also trigger models.dev refresh concurrently if requested
        mdev_future = None
        if update_models_dev:
            try:
                from agent.models_dev import fetch_models_dev

                mdev_future = executor.submit(fetch_models_dev, force_refresh=force_refresh)
            except Exception as exc:
                logger.debug("Failed to submit models.dev fetch: %s", exc)

        try:
            for future in concurrent.futures.as_completed(future_to_pid, timeout=timeout):
                pid = future_to_pid[future]
                try:
                    res = future.result()
                    provider_results[pid] = res
                except Exception as exc:
                    provider_results[pid] = {
                        "provider": pid,
                        "kind": "oauth" if pid in OAUTH_PROVIDERS else "api_key",
                        "status": "error",
                        "models": [],
                        "new_models": [],
                        "total": 0,
                        "error": str(exc),
                    }
        except TimeoutError:
            logger.warning("Model autoupdater timed out after %ss for some providers", timeout)
            for fut, pid in future_to_pid.items():
                if pid not in provider_results:
                    provider_results[pid] = {
                        "provider": pid,
                        "kind": "oauth" if pid in OAUTH_PROVIDERS else "api_key",
                        "status": "error",
                        "models": [],
                        "new_models": [],
                        "total": 0,
                        "error": f"timed out after {timeout}s",
                    }

        if mdev_future is not None:
            try:
                mdev_data = mdev_future.result(timeout=timeout)
                if isinstance(mdev_data, dict):
                    # Count total models across all providers in models.dev
                    models_dev_count = sum(
                        len(pinfo.get("models", {}))
                        for pinfo in mdev_data.values()
                        if isinstance(pinfo, dict)
                    )
            except Exception as exc:
                logger.debug("models.dev refresh failed: %s", exc)

    finally:
        executor.shutdown(wait=False, cancel_futures=True)
        with _UPDATE_LOCK:
            _IS_UPDATING = False

    duration = round(time.time() - start_time, 2)
    total_new = sum(len(res.get("new_models", [])) for res in provider_results.values())
    total_models = sum(res.get("total", 0) for res in provider_results.values())

    report = {
        "timestamp": start_time,
        "iso_timestamp": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": duration,
        "providers": provider_results,
        "models_dev_count": models_dev_count,
        "total_new_models": total_new,
        "total_models": total_models,
    }

    save_autoupdate_status(report)
    return report


def maybe_auto_update_models(*, background: bool = True) -> bool:
    """Check if model autoupdate is due and trigger it.

    Reads ``model_catalog.autoupdate`` (default True) and
    ``model_catalog.autoupdate_interval_hours`` (default 12) from config.

    Returns True if an update was initiated, False if skipped.
    """
    global _IS_UPDATING
    with _UPDATE_LOCK:
        if _IS_UPDATING:
            return False

    try:
        from jettstui.config import load_config

        config = load_config()
        catalog_cfg = config.get("model_catalog")
        if isinstance(catalog_cfg, dict):
            if not catalog_cfg.get("autoupdate", True):
                return False
            interval_hours = float(catalog_cfg.get("autoupdate_interval_hours", 12))
        else:
            interval_hours = 12.0

        status = get_autoupdate_status()
        last_run = float(status.get("timestamp", 0) or 0)
        elapsed_hours = (time.time() - last_run) / 3600.0

        if elapsed_hours < interval_hours:
            return False  # Still fresh

        with _UPDATE_LOCK:
            if _IS_UPDATING:
                return False
            _IS_UPDATING = True

        if background:
            try:
                t = threading.Thread(
                    target=update_all_models,
                    kwargs={"force_refresh": True, "update_models_dev": True, "lock_already_held": True},
                    name="model-autoupdater",
                    daemon=True,
                )
                t.start()
                return True
            except Exception:
                with _UPDATE_LOCK:
                    _IS_UPDATING = False
                raise
        else:
            update_all_models(force_refresh=True, update_models_dev=True, lock_already_held=True)
            return True
    except Exception as exc:
        logger.debug("maybe_auto_update_models check failed: %s", exc)
        return False


def format_update_report(report: dict[str, Any], *, use_color: bool = True) -> str:
    """Render a human-friendly summary of the model update results."""
    try:
        from jettstui.colors import Colors, color
    except Exception:
        use_color = False

    lines = []
    header = "◆ Model Catalog Auto-Update"
    lines.append(color(header, Colors.CYAN, Colors.BOLD) if use_color else header)

    providers = report.get("providers", {})
    if not providers:
        lines.append("  No providers configured for live update.")
    else:
        for pid, res in sorted(providers.items()):
            kind_badge = "[OAuth]" if res.get("kind") == "oauth" else "[API Key]"
            status = res.get("status")
            total = res.get("total", 0)
            new_models = res.get("new_models", [])

            if status == "error":
                msg = f"  ✗ {pid} {kind_badge}: error ({res.get('error')})"
                lines.append(color(msg, Colors.RED) if use_color else msg)
            elif new_models:
                new_names = ", ".join(new_models[:3])
                if len(new_models) > 3:
                    new_names += f" +{len(new_models) - 3} more"
                msg = f"  ✓ {pid} {kind_badge}: {total} models (+{len(new_models)} new: {new_names})"
                lines.append(color(msg, Colors.GREEN) if use_color else msg)
            else:
                msg = f"  ✓ {pid} {kind_badge}: {total} models (up to date)"
                lines.append(color(msg, Colors.DIM) if use_color else msg)

    mdev_count = report.get("models_dev_count", 0)
    if mdev_count:
        lines.append(f"  ✓ models.dev community registry: {mdev_count} models synced")

    duration = report.get("duration_seconds", 0)
    total_new = report.get("total_new_models", 0)
    summary = f"\n  Completed in {duration}s · {total_new} new model(s) discovered."
    lines.append(color(summary, Colors.BOLD) if use_color else summary)

    return "\n".join(lines)
