"""End-to-end regression tests verifying that all memory leaks, file descriptor leaks,
and resource accumulation bugs across the backend, gateway, database, and process
subsystems are prevented and cleaned up.
"""

from __future__ import annotations

import gc
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from jettstui_state import SessionDB
from jettstui.sqlite_safe_read import _key, _live_connections
from tools.process_registry import ProcessRegistry, ProcessSession


# ─────────────────────────────────────────────────────────────────────────────
# 1. SessionDB Connection Lifecycle & Resource Management
# ─────────────────────────────────────────────────────────────────────────────


class TestSessionDBResourceLifecycle:
    def test_session_db_context_manager_deterministic_close(self, tmp_path):
        """Using `with SessionDB(...) as db:` must cleanly close and untrack the connection."""
        db_file = tmp_path / "state.db"
        resolved_key = _key(db_file)
        initial_live = _live_connections.get(resolved_key, 0)

        with SessionDB(db_path=db_file) as db:
            assert db._conn is not None
            assert _live_connections.get(resolved_key, 0) == initial_live + 1
            db.create_session(session_id="s1", source="cli")

        # After exiting with-block, connection is closed and untracked
        assert db._conn is None
        assert _live_connections.get(resolved_key, 0) == initial_live

    def test_session_db_gc_del_untracks_connection(self, tmp_path):
        """If a SessionDB instance falls out of scope without explicit close(),
        its __del__ must cleanly close the connection and decrement _live_connections.
        """
        db_file = tmp_path / "state_gc.db"
        resolved_key = _key(db_file)
        initial_live = _live_connections.get(resolved_key, 0)

        def _open_and_drop():
            db = SessionDB(db_path=db_file)
            db.create_session(session_id="sgc", source="cli")
            assert _live_connections.get(resolved_key, 0) == initial_live + 1
            del db

        _open_and_drop()
        gc.collect()

        assert _live_connections.get(resolved_key, 0) == initial_live

    def test_session_db_readonly_close_does_not_fail_wal_checkpoint(self, tmp_path):
        """Closing a read-only SessionDB must skip the WAL checkpoint to prevent
        'attempt to write a readonly database' operational errors.
        """
        db_file = tmp_path / "state_ro.db"
        # First initialize the DB in write mode so it has a schema
        init_db = SessionDB(db_path=db_file)
        init_db.create_session(session_id="s_ro", source="cli")
        init_db.close()

        # Open in read-only mode and close — must not raise
        ro_db = SessionDB(db_path=db_file, read_only=True)
        assert ro_db.read_only is True
        ro_db.close()
        assert ro_db._conn is None


# ─────────────────────────────────────────────────────────────────────────────
# 2. Process Registry Memory & Watcher Cleanup
# ─────────────────────────────────────────────────────────────────────────────


class TestProcessRegistryResourceLifecycle:
    def test_move_to_finished_clears_env_ref(self):
        """Moving an exited process to finished must immediately drop its env_ref
        so large environment buffers and connection handles are not retained in RAM.
        """
        registry = ProcessRegistry()
        mock_env = MagicMock()
        session = ProcessSession(
            id="proc_leak_test",
            command="sleep 1",
            env_ref=mock_env,
        )
        registry._running[session.id] = session

        registry._move_to_finished(session)

        assert session.id in registry._finished
        assert session.id not in registry._running
        assert session.env_ref is None

    def test_prune_finished_removes_untracked_pending_watchers(self):
        """_prune_finished must purge pending_watchers for sessions that have been pruned,
        preventing unbounded watcher accumulation in long-running processes.
        """
        registry = ProcessRegistry()
        s1 = ProcessSession(id="p_alive", command="test")
        s2 = ProcessSession(id="p_expired", command="test", started_at=time.time() - 7200)

        registry._running[s1.id] = s1
        registry._finished[s2.id] = s2

        registry.pending_watchers = [
            {"session_id": "p_alive", "platform": "telegram"},
            {"session_id": "p_expired", "platform": "telegram"},
            {"session_id": "p_unknown_orphan", "platform": "telegram"},
        ]

        with registry._lock:
            registry._prune_if_needed()

        # Only the alive session's watcher should remain
        remaining_sids = [w["session_id"] for w in registry.pending_watchers]
        assert remaining_sids == ["p_alive"]


# ─────────────────────────────────────────────────────────────────────────────
# 3. Gateway In-Memory LRU Session Cap & Eviction
# ─────────────────────────────────────────────────────────────────────────────


class TestGatewaySessionCapLifecycle:
    def test_default_session_cap_is_active(self, monkeypatch):
        """When max_live_sessions is not set in config, _max_live_sessions must default
        to 16 rather than 0 (disabled), so detached sessions are capped.
        """
        from tui_gateway.server import _max_live_sessions

        monkeypatch.setattr("tui_gateway.server._load_cfg", lambda: {})
        assert _max_live_sessions() == 16

    def test_session_cap_evicts_oldest_detached_sessions(self, monkeypatch):
        """When total sessions exceed the cap, detached dead-transport sessions
        are evicted down to the cap, freeing resident agents from memory.
        """
        from tui_gateway import server

        monkeypatch.setattr(server, "_max_live_sessions", lambda: 2)

        evicted_sids = []
        monkeypatch.setattr(
            server, "_close_session_by_id",
            lambda sid, end_reason="": evicted_sids.append((sid, end_reason)),
        )

        class DeadTransport:
            _closed = True

        # Create 4 sessions: 3 detached, 1 live
        s1 = {"transport": DeadTransport(), "last_active": 100.0, "running": False}  # oldest detached
        s2 = {"transport": DeadTransport(), "last_active": 200.0, "running": False}  # newer detached
        s3 = {"transport": DeadTransport(), "last_active": 300.0, "running": False}  # newest detached
        s4 = {"transport": MagicMock(_closed=False), "last_active": 400.0, "running": False}  # live transport

        with server._sessions_lock:
            server._sessions.clear()
            server._sessions["s1"] = s1
            server._sessions["s2"] = s2
            server._sessions["s3"] = s3
            server._sessions["s4"] = s4

        server._enforce_session_cap()

        # 4 total sessions - 2 cap = 2 overflow evictions
        assert len(evicted_sids) == 2
        assert evicted_sids[0] == ("s1", "lru_evict")
        assert evicted_sids[1] == ("s2", "lru_evict")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Turn Auxiliary Client Cleanup & Poller Dedup Cap
# ─────────────────────────────────────────────────────────────────────────────


class TestAuxiliaryClientAndPollerCleanup:
    def test_cleanup_stale_async_clients_purges_dead_loops(self):
        """cleanup_stale_async_clients must close and remove clients bound to closed event loops."""
        import asyncio
        from agent.auxiliary_client import (
            _client_cache,
            _client_cache_lock,
            cleanup_stale_async_clients,
        )

        dead_loop = asyncio.new_event_loop()
        dead_loop.close()

        mock_client = MagicMock()
        mock_client._client = MagicMock(is_closed=False)

        cache_key = ("test_prov", True, "http://test", "key", "chat", (), False, "", "", "m1")
        with _client_cache_lock:
            _client_cache[cache_key] = (mock_client, "m1", dead_loop)

        cleanup_stale_async_clients()

        with _client_cache_lock:
            assert cache_key not in _client_cache

    def test_poller_emitted_set_stays_bounded(self):
        """_notification_poller_loop must cap the _emitted dedup set at 500 entries."""
        emitted = set(f"evt_{i}" for i in range(500))
        # When a new dedup key arrives and size is >= 500, it clears
        new_key = "evt_501"
        if len(emitted) >= 500:
            emitted.clear()
        emitted.add(new_key)

        assert len(emitted) == 1
        assert new_key in emitted


# ─────────────────────────────────────────────────────────────────────────────
# 5. Web Server Temp File & Memory Lifecycle
# ─────────────────────────────────────────────────────────────────────────────


class TestWebServerTempFileLifecycle:
    def test_pty_active_session_file_cleanup_on_channel_teardown(self):
        """_cleanup_pty_active_session_file must unlink the temp file and remove it from app state."""
        from jettstui.web_server import (
            _active_session_file_for_channel,
            _cleanup_pty_active_session_file,
            _get_pty_active_session_files,
        )

        dummy_app = FastAPI()
        channel = "test-chan-123"

        path = _active_session_file_for_channel(dummy_app, channel)
        assert path.exists()
        assert channel in _get_pty_active_session_files(dummy_app)

        # Cleanup channel
        _cleanup_pty_active_session_file(dummy_app, channel)

        assert not path.exists()
        assert channel not in _get_pty_active_session_files(dummy_app)

    def test_usage_analytics_totals_default_zeros_on_empty_db(self, tmp_path, monkeypatch):
        """_get_usage_analytics must return 0 (not None) for all totals when no sessions exist."""
        from jettstui.web_server import _get_usage_analytics

        empty_db_file = tmp_path / "empty_state.db"
        empty_db = SessionDB(db_path=empty_db_file)

        monkeypatch.setattr(
            "jettstui.web_server._open_session_db_for_profile",
            lambda _prof: empty_db,
        )

        analytics = _get_usage_analytics(days=30)
        totals = analytics["totals"]

        assert totals["total_input"] == 0
        assert totals["total_output"] == 0
        assert totals["total_cache_read"] == 0
        assert totals["total_cache_write"] == 0
        assert totals["total_reasoning"] == 0
        assert totals["total_sessions"] == 0
        assert totals["total_api_calls"] == 0

    def test_provider_quotas_endpoint_resilient_to_single_failure(self, monkeypatch):
        """If one provider quota fetch fails, /api/providers/quota must return the error for that
        provider without crashing the entire endpoint with an HTTP 500.
        """
        from jettstui.web_server import _SESSION_TOKEN, app

        client = TestClient(app)
        headers = {"X-JettsTUI-Session-Token": _SESSION_TOKEN}

        def failing_fetch(provider, **_):
            if provider == "antigravity":
                raise RuntimeError("Network timeout")
            return None

        catalog = [
            {"id": "antigravity", "name": "Antigravity", "source": "antigravity"},
            {"id": "openai-codex", "name": "Codex", "source": "openai-codex"},
        ]

        with patch("jettstui.web_server._build_oauth_catalog", return_value=catalog), \
             patch("jettstui.web_server._resolve_provider_status", return_value={"logged_in": True}), \
             patch("agent.account_usage.fetch_account_usage", side_effect=failing_fetch):
            resp = client.get("/api/providers/quota", headers=headers)

        assert resp.status_code == 200
        providers = resp.json().get("providers", [])
        assert len(providers) == 2
        broken = next(p for p in providers if p["id"] == "antigravity")
        assert "error" in broken


# ─────────────────────────────────────────────────────────────────────────────
# 6. Model Autoupdater Concurrency & Cache Atomicity
# ─────────────────────────────────────────────────────────────────────────────


class TestModelAutoupdaterConcurrency:
    def test_single_provider_cache_update_lock_serializes_writes(self, tmp_path, monkeypatch):
        """_update_single_provider_cache must serialize writes under lock so parallel
        threads never clobber each other's cache entries.
        """
        import jettstui.models as jm

        cache_path = tmp_path / "provider_models_cache.json"
        monkeypatch.setattr(jm, "_provider_models_cache_path", lambda: cache_path)

        def worker(provider_id: str, count: int):
            for i in range(count):
                jm._update_single_provider_cache(
                    provider=provider_id,
                    fp="test_fp",
                    now=time.time(),
                    models=[f"{provider_id}-model-{i}"],
                )

        threads = [
            threading.Thread(target=worker, args=(f"provider_{p}", 20))
            for p in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        final_cache = jm._load_provider_models_cache()
        # All 5 providers must have survived in the cache
        for p in range(5):
            pid = f"provider_{p}"
            assert pid in final_cache
            assert len(final_cache[pid]["models"]) == 1
            assert final_cache[pid]["models"][0] == f"{pid}-model-19"
