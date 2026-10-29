"""Jetts Bots: named teammates inside one profile (agent/bots.py + its callers)."""

from __future__ import annotations

import argparse
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agent import bots
from jettstui_constants import get_jettstui_home


def test_create_list_update_and_remove_archives_memory():
    bot = bots.create_bot("Sales Outbound", "Draft outreach; never send without OK.")
    assert bot["id"] == "sales-outbound"
    (bots.bots_dir() / "sales-outbound" / "MEMORY.md").write_text("Acme signs annual\n", encoding="utf-8")

    assert [b["id"] for b in bots.list_bots()] == ["sales-outbound"]
    assert bots.update_bot("sales-outbound", session_id="s1")["session_id"] == "s1"

    archived = bots.remove_bot("sales-outbound")
    assert bots.list_bots() == []
    assert (archived / "MEMORY.md").read_text(encoding="utf-8") == "Acme signs annual\n"


@pytest.mark.parametrize("name,role", [("", "x"), ("!!!", "x"), ("ok", ""), ("ok", "x" * 2001)])
def test_invalid_bots_are_rejected(name, role):
    with pytest.raises(ValueError):
        bots.create_bot(name, role)


def test_duplicate_and_path_traversal_ids_are_rejected():
    bots.create_bot("Scout", "Find talent")
    with pytest.raises(ValueError):
        bots.create_bot("scout", "again")
    for bad in ("../x", "a/b", "..", ""):
        with pytest.raises(ValueError):
            bots.get_bot(bad)


def test_apply_bot_sets_role_and_splits_memory_but_shares_the_user():
    from tools.memory_tool import MemoryStore

    bots.create_bot("Scout", "Find talent")
    shared = MemoryStore()
    shared.load_from_disk()
    shared.add("user", "Prefers short emails")
    shared.add("memory", "Profile-wide note")
    agent = SimpleNamespace(ephemeral_system_prompt="Base persona", _memory_store=shared)

    bots.apply_bot(agent, "scout")

    assert agent.ephemeral_system_prompt.startswith("Base persona\n\n")
    assert "Your job: Find talent" in agent.ephemeral_system_prompt
    store = agent._memory_store
    assert store.user_entries == ["Prefers short emails"]
    assert store.memory_entries == []
    store.add("memory", "Dana approves offers")
    assert (bots.bots_dir() / "scout" / "MEMORY.md").exists()
    assert "Dana approves offers" not in (get_jettstui_home() / "memories" / "MEMORY.md").read_text(encoding="utf-8")


def test_bot_for_session_follows_compression_and_branch_parents():
    bots.create_bot("Scout", "Find talent")
    bots.update_bot("scout", session_id="root")
    parents = {"tip": {"parent_session_id": "mid"}, "mid": {"parent_session_id": "root"}}
    db = SimpleNamespace(get_session=lambda sid: parents.get(sid))

    assert bots.bot_for_session("tip", db) == "scout"
    assert bots.bot_for_session("unrelated", db) is None


class TestGatewayBinding:
    def _apply(self, sid_bot, session_id, db):
        from tui_gateway import server

        agent = SimpleNamespace(ephemeral_system_prompt=None, _memory_store=None)
        with patch.dict(server._sessions, {"sid": {"bot": sid_bot}}, clear=False):
            server._apply_session_bot(agent, "sid", session_id, db)
        return agent

    def test_new_chat_with_a_bot_becomes_its_thread(self):
        bots.create_bot("Scout", "Find talent")
        db = SimpleNamespace(get_session=lambda sid: None)
        agent = self._apply("scout", "new-session", db)
        assert agent.jetts_bot == "scout"
        assert bots.get_bot("scout")["session_id"] == "new-session"

    def test_resume_and_branch_reuse_the_bot_without_stealing_its_thread(self):
        bots.create_bot("Scout", "Find talent")
        bots.update_bot("scout", session_id="thread")
        db = SimpleNamespace(get_session=lambda sid: {"parent_session_id": "thread"} if sid == "branch" else None)
        agent = self._apply(None, "branch", db)
        assert agent.jetts_bot == "scout"
        assert bots.get_bot("scout")["session_id"] == "thread"

    def test_removed_bot_leaves_a_normal_session(self):
        db = SimpleNamespace(get_session=lambda sid: None)
        agent = self._apply("ghost", "s", db)
        assert not hasattr(agent, "jetts_bot")


class TestRoutines:
    def test_cron_job_carries_its_bot_and_rejects_unknown_bots(self):
        from cron.jobs import create_job

        bots.create_bot("Weekly Reporting", "Summarize the week")
        assert create_job("Summarize commits", "0 9 * * 5", bot="weekly-reporting")["bot"] == "weekly-reporting"
        with pytest.raises(ValueError):
            create_job("x", "0 9 * * 5", bot="ghost")

    def test_routine_scheduled_from_a_bot_thread_is_tagged_with_that_bot(self):
        import json

        from tools.cronjob_tools import cronjob

        bots.create_bot("Weekly Reporting", "Summarize the week")
        bots.update_bot("weekly-reporting", session_id="thread")
        with patch("agent.bots.bot_for_session", return_value="weekly-reporting") as lookup:
            res = json.loads(cronjob(action="create", prompt="Summarize", schedule="0 9 * * 5", session_id="thread"))
        lookup.assert_called_once_with("thread")
        assert res["job"]["bot"] == "weekly-reporting"


def test_cli_create_list_remove(capsys):
    from jettstui.bots_cmd import bots_command

    def run(**kw):
        return bots_command(argparse.Namespace(**kw))

    assert run(bot_action="create", name="Scout", role="Find talent", model=None, provider=None) == 0
    assert run(bot_action="list", json=False) == 0
    assert "scout" in capsys.readouterr().out
    assert run(bot_action="remove", bot="scout") == 0
    assert run(bot_action="remove", bot="scout") == 1
