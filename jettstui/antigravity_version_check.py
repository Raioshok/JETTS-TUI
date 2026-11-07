"""Antigravity client version auto-updater.

Fetches the latest Google Antigravity app version from the VSCode Marketplace
API and caches it to ``$JETTSTUI_HOME/antigravity_client_version.json``.
``_antigravity_client_version()`` reads the cache file so the headers sent to
the Cloud Code PA backend always match the current official release, without
requiring a code change or a restart.

Design constraints (AGENTS.md):
- Runs in a daemon background thread — zero startup latency for the user.
- Cache is valid for ``check_interval_hours`` (default 6h, min 1h).
- Falls back silently to the hardcoded ``ANTIGRAVITY_VERSION`` constant on any
  network/parse error; never raises.
- No new env-var config — interval is read from
  ``providers.antigravity.version_check_interval_hours`` in ``config.yaml``.
- Fetches only the VSCode Marketplace API endpoint (public, no auth).
  Secondary source: GitHub releases page for google/antigravity.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import Any, Optional

from utils import atomic_json_write

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Cache file & interval
# ------------------------------------------------------------------
_CACHE_FILENAME = "antigravity_client_version.json"
_DEFAULT_CHECK_INTERVAL_HOURS = 6.0
_MIN_CHECK_INTERVAL_HOURS = 1.0

# VSCode Marketplace query for the official Antigravity extension.
# Returns JSON with the latest version among its versions array.
_VSCODE_MARKETPLACE_URL = (
    "https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery"
)
_MARKETPLACE_HEADERS = {
    "Accept": "application/json;api-version=7.1-preview.1",
    "Content-Type": "application/json",
}
_MARKETPLACE_BODY = {
    "filters": [
        {
            "criteria": [
                {"filterType": 7, "value": "google.googleantigravity"},
            ],
            "pageNumber": 1,
            "pageSize": 1,
        }
    ],
    "assetTypes": [],
    "flags": 0x200,  # IncludeLatestVersionOnly
}

# Fallback: GitHub releases API
_GITHUB_RELEASES_URL = (
    "https://api.github.com/repos/google/antigravity/releases/latest"
)

# Semver-like version pattern (matches "2.31.0", "v2.31.0", etc.)
_VERSION_RE = re.compile(r"(\d+\.\d+\.\d+)")


def _get_cache_path() -> Path:
    from jettstui_constants import get_jettstui_home

    return get_jettstui_home() / _CACHE_FILENAME


def _load_cache() -> dict[str, Any]:
    path = _get_cache_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.debug("antigravity_version_check: failed to read cache: %s", exc)
        return {}


def _save_cache(version: str) -> None:
    path = _get_cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json_write(
            path,
            {"version": version, "timestamp": time.time()},
            indent=2,
        )
        logger.debug(
            "antigravity_version_check: cached version %s → %s", version, path
        )
    except Exception as exc:
        logger.debug("antigravity_version_check: failed to save cache: %s", exc)


def get_cached_version() -> Optional[str]:
    """Return the last successfully fetched version, or None if cache is empty."""
    cache = _load_cache()
    v = cache.get("version")
    return str(v).strip() if v and isinstance(v, str) else None


def _is_cache_stale(interval_hours: float) -> bool:
    cache = _load_cache()
    ts = cache.get("timestamp")
    if not ts:
        return True
    elapsed_hours = (time.time() - float(ts)) / 3600.0
    return elapsed_hours >= interval_hours


def _fetch_from_marketplace(http_client: Any) -> Optional[str]:
    """Query VSCode Marketplace for the latest google.googleantigravity version."""
    try:
        resp = http_client.post(
            _VSCODE_MARKETPLACE_URL,
            json=_MARKETPLACE_BODY,
            headers=_MARKETPLACE_HEADERS,
            timeout=10.0,
        )
        if resp.status_code != 200:
            logger.debug(
                "antigravity_version_check: marketplace HTTP %d", resp.status_code
            )
            return None
        data = resp.json()
        exts = (
            data.get("results", [{}])[0]
            .get("extensions", [{}])
        )
        if not exts:
            return None
        versions = exts[0].get("versions", [])
        if not versions:
            return None
        raw = versions[0].get("version", "")
        # Marketplace version may be "1.0.261026.0" style — extract semver portion
        # or take the raw string if it already looks like semver.
        m = _VERSION_RE.search(raw)
        if m:
            return m.group(1)
        return None
    except Exception as exc:
        logger.debug("antigravity_version_check: marketplace fetch error: %s", exc)
        return None


def _fetch_from_github(http_client: Any) -> Optional[str]:
    """Query GitHub releases API for the latest Antigravity release tag."""
    try:
        resp = http_client.get(
            _GITHUB_RELEASES_URL,
            headers={"Accept": "application/vnd.github+json"},
            timeout=10.0,
        )
        if resp.status_code != 200:
            return None
        tag = resp.json().get("tag_name", "")
        m = _VERSION_RE.search(tag)
        return m.group(1) if m else None
    except Exception as exc:
        logger.debug("antigravity_version_check: github fetch error: %s", exc)
        return None


def fetch_latest_version() -> Optional[str]:
    """Fetch the latest Antigravity version from remote sources.

    Tries VSCode Marketplace first, then GitHub releases.
    Returns the version string on success, None on failure.
    """
    try:
        import httpx  # already a dependency via antigravity_adapter

        with httpx.Client(timeout=12.0) as client:
            version = _fetch_from_marketplace(client)
            if version:
                logger.info(
                    "antigravity_version_check: marketplace → %s", version
                )
                return version
            version = _fetch_from_github(client)
            if version:
                logger.info(
                    "antigravity_version_check: github → %s", version
                )
                return version
    except Exception as exc:
        logger.debug("antigravity_version_check: fetch failed: %s", exc)
    return None


def _get_check_interval_hours() -> float:
    try:
        from jettstui.config import load_config

        cfg = load_config()
        v = (
            cfg.get("providers", {})
            .get("antigravity", {})
            .get("version_check_interval_hours", _DEFAULT_CHECK_INTERVAL_HOURS)
        )
        return max(_MIN_CHECK_INTERVAL_HOURS, float(v))
    except Exception:
        return _DEFAULT_CHECK_INTERVAL_HOURS


def maybe_check_antigravity_version(*, background: bool = True) -> bool:
    """Check if the Antigravity client version cache needs refreshing and update it.

    Called at startup from ``model_autoupdater.maybe_auto_update_models()`` so
    it piggybacks on the existing periodic background sweep.

    Returns True if a check was initiated, False if the cache is still fresh.
    """
    interval = _get_check_interval_hours()
    if not _is_cache_stale(interval):
        return False

    def _do_check() -> None:
        try:
            version = fetch_latest_version()
            if version:
                _save_cache(version)
        except Exception as exc:
            logger.debug("antigravity_version_check: background check error: %s", exc)

    if background:
        t = threading.Thread(
            target=_do_check,
            name="antigravity-version-check",
            daemon=True,
        )
        t.start()
    else:
        _do_check()

    return True
