"""Tests for jettstui.antigravity_version_check."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest import mock

import httpx
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _marketplace_response(version: str = "2.30.0") -> dict:
    """Minimal VSCode Marketplace response payload."""
    return {
        "results": [
            {
                "extensions": [
                    {
                        "versions": [{"version": version}]
                    }
                ]
            }
        ]
    }


def _github_response(tag: str = "v2.30.0") -> dict:
    return {"tag_name": tag}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFetchLatestVersion:
    def test_marketplace_success_returns_semver(self, tmp_path, monkeypatch):
        """Happy-path: marketplace returns a semver version."""
        from jettstui import antigravity_version_check as avc

        resp = mock.MagicMock()
        resp.status_code = 200
        resp.json.return_value = _marketplace_response("2.30.0")

        with mock.patch("httpx.Client") as mock_cls:
            mock_client = mock_cls.return_value.__enter__.return_value
            mock_client.post.return_value = resp
            mock_client.get.return_value = mock.MagicMock(status_code=404, json=lambda: {})
            version = avc.fetch_latest_version()

        assert version == "2.30.0"

    def test_marketplace_non_semver_version_string_is_extracted(self, monkeypatch):
        """Marketplace can return '1.0.261026.0' — extract the first semver chunk."""
        from jettstui import antigravity_version_check as avc

        resp = mock.MagicMock()
        resp.status_code = 200
        resp.json.return_value = _marketplace_response("1.0.261026.0")

        with mock.patch("httpx.Client") as mock_cls:
            mock_client = mock_cls.return_value.__enter__.return_value
            mock_client.post.return_value = resp
            version = avc._fetch_from_marketplace(mock_client)

        # Should extract first semver-like triple
        assert version is not None
        import re
        assert re.match(r"\d+\.\d+\.\d+", version)

    def test_github_fallback_when_marketplace_fails(self, monkeypatch):
        """Falls back to GitHub releases when marketplace returns non-200."""
        from jettstui import antigravity_version_check as avc

        mp_resp = mock.MagicMock()
        mp_resp.status_code = 500

        gh_resp = mock.MagicMock()
        gh_resp.status_code = 200
        gh_resp.json.return_value = _github_response("v2.31.0")

        with mock.patch("httpx.Client") as mock_cls:
            mock_client = mock_cls.return_value.__enter__.return_value
            mock_client.post.return_value = mp_resp
            mock_client.get.return_value = gh_resp
            version = avc.fetch_latest_version()

        assert version == "2.31.0"

    def test_returns_none_when_all_sources_fail(self, monkeypatch):
        """Returns None gracefully when both sources fail."""
        from jettstui import antigravity_version_check as avc

        err_resp = mock.MagicMock()
        err_resp.status_code = 503

        with mock.patch("httpx.Client") as mock_cls:
            mock_client = mock_cls.return_value.__enter__.return_value
            mock_client.post.return_value = err_resp
            mock_client.get.return_value = err_resp
            version = avc.fetch_latest_version()

        assert version is None

    def test_returns_none_on_network_error(self):
        """Returns None when httpx raises (network down, DNS failure, etc.)."""
        from jettstui import antigravity_version_check as avc

        with mock.patch("httpx.Client") as mock_cls:
            mock_cls.return_value.__enter__.side_effect = httpx.ConnectError("unreachable")
            version = avc.fetch_latest_version()

        assert version is None


class TestCacheReadWrite:
    def test_save_and_get_cached_version(self, tmp_path, monkeypatch):
        """save_cache → get_cached_version round-trip."""
        from jettstui import antigravity_version_check as avc

        monkeypatch.setattr(avc, "_get_cache_path", lambda: tmp_path / "avc.json")

        # Patch atomic_json_write to plain json.dump
        def _plain_write(path, data, **kw):
            Path(path).write_text(json.dumps(data))

        with mock.patch("jettstui.antigravity_version_check.atomic_json_write", _plain_write):
            avc._save_cache("2.32.0")

        result = avc.get_cached_version()
        assert result == "2.32.0"

    def test_get_cached_version_returns_none_when_no_cache(self, tmp_path, monkeypatch):
        from jettstui import antigravity_version_check as avc

        monkeypatch.setattr(avc, "_get_cache_path", lambda: tmp_path / "missing.json")
        assert avc.get_cached_version() is None

    def test_cache_staleness_check(self, tmp_path, monkeypatch):
        """Cache written now is fresh; cache with old timestamp is stale."""
        from jettstui import antigravity_version_check as avc

        cache_path = tmp_path / "avc.json"
        monkeypatch.setattr(avc, "_get_cache_path", lambda: cache_path)

        # Fresh cache
        cache_path.write_text(json.dumps({"version": "2.29.0", "timestamp": time.time()}))
        assert avc._is_cache_stale(6.0) is False

        # Stale cache (25 hours ago)
        cache_path.write_text(json.dumps({"version": "2.29.0", "timestamp": time.time() - 25 * 3600}))
        assert avc._is_cache_stale(6.0) is True

        # No cache at all → stale
        cache_path.unlink()
        assert avc._is_cache_stale(6.0) is True


class TestMaybeCheck:
    def test_skips_when_cache_is_fresh(self, tmp_path, monkeypatch):
        """maybe_check_antigravity_version returns False when cache is not stale."""
        from jettstui import antigravity_version_check as avc

        monkeypatch.setattr(avc, "_is_cache_stale", lambda _interval: False)
        result = avc.maybe_check_antigravity_version(background=False)
        assert result is False

    def test_runs_check_when_stale(self, tmp_path, monkeypatch):
        """maybe_check_antigravity_version runs synchronously when stale."""
        from jettstui import antigravity_version_check as avc

        monkeypatch.setattr(avc, "_is_cache_stale", lambda _interval: True)

        saved = []

        def _fake_fetch():
            return "2.33.0"

        def _fake_save(v):
            saved.append(v)

        monkeypatch.setattr(avc, "fetch_latest_version", _fake_fetch)
        monkeypatch.setattr(avc, "_save_cache", _fake_save)

        result = avc.maybe_check_antigravity_version(background=False)
        assert result is True
        assert saved == ["2.33.0"]

    def test_handles_fetch_failure_gracefully(self, monkeypatch):
        """maybe_check never raises even if fetch fails."""
        from jettstui import antigravity_version_check as avc

        monkeypatch.setattr(avc, "_is_cache_stale", lambda _interval: True)
        monkeypatch.setattr(avc, "fetch_latest_version", lambda: None)

        # Should not raise
        avc.maybe_check_antigravity_version(background=False)


class TestVersionResolverIntegration:
    def test_cached_version_is_used_by_antigravity_client_version(self, tmp_path, monkeypatch):
        """_antigravity_client_version() returns the auto-fetched cached version."""
        from jettstui import antigravity_version_check as avc
        from jettstui import antigravity_auth

        # Patch config to return no manual override
        monkeypatch.setattr(
            "jettstui.config.load_config",
            lambda: {},
            raising=False,
        )
        # Patch get_cached_version to return auto-fetched version
        monkeypatch.setattr(avc, "get_cached_version", lambda: "2.35.0")

        result = antigravity_auth._antigravity_client_version()
        assert result == "2.35.0"

    def test_config_yaml_takes_precedence_over_cache(self, monkeypatch):
        """Manual config.yaml pin beats the auto-fetched cache."""
        from jettstui import antigravity_version_check as avc
        from jettstui import antigravity_auth

        monkeypatch.setattr(
            "jettstui.config.load_config",
            lambda: {"providers": {"antigravity": {"client_version": "2.99.0"}}},
            raising=False,
        )
        monkeypatch.setattr(avc, "get_cached_version", lambda: "2.35.0")

        result = antigravity_auth._antigravity_client_version()
        assert result == "2.99.0"

    def test_falls_back_to_hardcoded_when_cache_empty(self, monkeypatch):
        """Falls back to ANTIGRAVITY_VERSION when neither config nor cache has a value."""
        from jettstui import antigravity_version_check as avc
        from jettstui import antigravity_auth

        monkeypatch.setattr(
            "jettstui.config.load_config",
            lambda: {},
            raising=False,
        )
        monkeypatch.setattr(avc, "get_cached_version", lambda: None)

        result = antigravity_auth._antigravity_client_version()
        assert result == antigravity_auth.ANTIGRAVITY_VERSION
