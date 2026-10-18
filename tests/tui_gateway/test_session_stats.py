"""session.stats: working time + est cost for any stored session."""

import pytest

from jettstui_state import SessionDB
import tui_gateway.server as server


@pytest.fixture
def db(tmp_path, monkeypatch):
    database = SessionDB(tmp_path / "state.db")
    monkeypatch.setattr(server, "_get_db", lambda: database)
    monkeypatch.setattr(server, "_sessions", {}, raising=False)
    return database


def _stats(sid):
    return server._methods["session.stats"]("r", {"session_id": sid})


def test_active_seconds_accumulate_per_api_call(db):
    db.create_session("s1", source="desktop")
    db.update_token_counts("s1", input_tokens=100, output_tokens=20, model="gpt-5.6-sol", active_seconds=4.0, api_call_count=1)
    db.update_token_counts("s1", input_tokens=50, output_tokens=10, model="gpt-5.6-sol", active_seconds=2.5, api_call_count=1)

    result = _stats("s1")["result"]
    assert result["active_seconds"] == pytest.approx(6.5)
    assert result["api_call_count"] == 2
    assert result["total_tokens"] == 180


def test_cost_is_estimated_from_stored_tokens(db):
    db.create_session("s2", source="desktop")
    # A model with known published pricing — cost must be a positive number.
    db.update_token_counts(
        "s2", input_tokens=1_000_000, output_tokens=1_000_000,
        model="gpt-5.6-sol", billing_provider="openai", api_call_count=1, active_seconds=10.0,
    )
    result = _stats("s2")["result"]
    assert result["cost_usd"] is not None and result["cost_usd"] > 0
    assert result["model"] == "gpt-5.6-sol"


def test_stats_resolve_by_id_prefix(db):
    db.create_session("20260101_120000_abcdef", source="desktop")
    db.update_token_counts("20260101_120000_abcdef", input_tokens=5, output_tokens=5, active_seconds=1.0, api_call_count=1)
    result = _stats("20260101_120000")["result"]
    assert result["session_id"] == "20260101_120000_abcdef"


def test_unknown_session_errors(db):
    resp = _stats("does-not-exist")
    assert resp["error"]["code"] == 4015


def test_missing_session_id_errors(db):
    resp = server._methods["session.stats"]("r", {})
    assert resp["error"]["code"] == 4004
