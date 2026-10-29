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


class TestBackgroundTasks:
    def _rpc(self, overrides):
        from tui_gateway import server

        return patch.dict(server._methods, overrides)

    def test_task_starts_a_thread_when_the_bot_has_none_and_submits_it(self):
        from tui_gateway import server

        bots.create_bot("Scout", "Find talent")
        calls = []

        def create(rid, params):
            calls.append(("create", params.get("bot")))
            return {"result": {"session_id": "live1", "stored_session_id": "stored1"}}

        def submit(rid, params):
            calls.append(("submit", params["session_id"], params["text"]))
            return {"result": {"status": "streaming"}}

        with self._rpc({"session.create": create, "prompt.submit": submit}):
            res = server._methods["bots.assign"]("r", {"id": "scout", "task": "Find 3 Rust devs"})
        assert res["result"] == {"session_id": "live1", "stored_session_id": "stored1"}
        assert calls == [("create", "scout"), ("submit", "live1", "Find 3 Rust devs")]

    def test_task_resumes_the_existing_thread_and_falls_back_when_it_is_gone(self):
        from tui_gateway import server

        bots.create_bot("Scout", "Find talent")
        bots.update_bot("scout", session_id="thread")
        seen = []
        resume = lambda rid, p: seen.append(("resume", p["session_id"])) or {"error": {"code": 4007}}
        create = lambda rid, p: seen.append(("create", p["bot"])) or {"result": {"session_id": "live2"}}
        submit = lambda rid, p: {"result": {}}
        with self._rpc({"session.resume": resume, "session.create": create, "prompt.submit": submit}):
            res = server._methods["bots.assign"]("r", {"id": "scout", "task": "go"})
        assert seen == [("resume", "thread"), ("create", "scout")]
        assert res["result"]["session_id"] == "live2"

    def test_empty_task_and_unknown_bot_are_rejected(self):
        from tui_gateway import server

        assert "error" in server._methods["bots.assign"]("r", {"id": "ghost", "task": "x"})
        bots.create_bot("Scout", "Find talent")
        assert "error" in server._methods["bots.assign"]("r", {"id": "scout", "task": "  "})

    def test_status_reports_working_and_waiting_on_approval(self):
        from tui_gateway import server

        bots.create_bot("Scout", "Find talent")
        live = {"a": {"bot": "scout", "running": True, "session_key": "k1"}}
        with patch.dict(server._sessions, live):
            assert server._bot_status("scout") == "working"
            with patch("tools.approval.has_blocking_approval", side_effect=lambda key: key == "k1"):
                assert server._bot_status("scout") == "needs_you"
        assert server._bot_status("scout") == "idle"

    def test_task_for_a_bot_already_open_queues_on_that_thread(self):
        from tui_gateway import server

        bots.create_bot("Scout", "Find talent")
        submitted = []
        submit = lambda rid, p: submitted.append(p) or {"result": {}}
        create = lambda rid, p: pytest.fail("must not open a second thread")
        with self._rpc({"prompt.submit": submit, "session.create": create}), \
             patch.dict(server._sessions, {"live9": {"bot": "scout"}}):
            res = server._methods["bots.assign"]("r", {"id": "scout", "task": "next"})
        assert res["result"]["session_id"] == "live9"
        assert submitted == [{"session_id": "live9", "text": "next", "queued": True}]


class TestBotComputer:
    @pytest.fixture(autouse=True)
    def _bot_with_computer(self):
        from tools.computer_use import tool as cu

        bots.create_bot("Scout", "Find talent")
        bots.update_bot("scout", session_id="bot-thread")
        bots.set_bot_computer("Lab-VM")
        cu.reset_backend_for_tests()
        cu.set_approval_callback(lambda *a: "approve_once")
        yield
        cu.set_approval_callback(None)
        cu.reset_backend_for_tests()

    def _call(self, args, session_id):
        from tools.computer_use import tool as cu

        db = SimpleNamespace(get_session=lambda sid: None)
        with patch("jettstui_state.SessionDB", return_value=db), \
             patch("tools.computer_use.vm_manager.VMManager.handle_action", return_value='{"ok": true}') as vm, \
             patch.dict("os.environ", {"JETTSTUI_COMPUTER_USE_BACKEND": "noop"}):
            out = cu.handle_computer_use(dict(args), session_id=session_id)
        return out, vm

    def test_bot_desktop_actions_go_to_the_bots_computer(self):
        _, vm = self._call({"action": "click", "coordinate": [1, 2]}, "bot-thread")
        assert vm.call_args.args[1]["target"] == "Lab-VM"

    def test_bot_cannot_reach_the_users_desktop(self):
        import json

        out, vm = self._call({"action": "type", "text": "x", "target": "host"}, "bot-thread")
        assert "off-limits" in json.loads(out)["error"]
        vm.assert_not_called()

    def test_ordinary_chats_are_unaffected(self):
        _, vm = self._call({"action": "click", "coordinate": [1, 2]}, "someone-else")
        vm.assert_not_called()

    def test_prompt_names_the_computer_only_when_computer_use_is_available(self):
        with_tool = SimpleNamespace(ephemeral_system_prompt=None, _memory_store=None, valid_tool_names={"computer_use"})
        without = SimpleNamespace(ephemeral_system_prompt=None, _memory_store=None, valid_tool_names=set())
        bots.apply_bot(with_tool, "scout")
        bots.apply_bot(without, "scout")
        assert "'Lab-VM'" in with_tool.ephemeral_system_prompt
        assert "Lab-VM" not in without.ephemeral_system_prompt

    def test_open_computer_opens_the_configured_vm_console(self):
        from tui_gateway import server

        with patch("tools.computer_use.vm_manager.VMManager.open_console",
                   return_value={"ok": True, "message": "opened"}) as open_console:
            res = server._methods["bots.open_computer"]("r", {})
        open_console.assert_called_once_with("Lab-VM")
        assert res["result"]["ok"] is True
        bots.set_bot_computer(None)
        assert "error" in server._methods["bots.open_computer"]("r", {})


def test_hyperv_console_launches_vmconnect_for_that_vm():
    from tools.computer_use.vm_manager import HyperVProvider

    with patch("os.path.exists", return_value=True), patch("subprocess.Popen") as popen:
        assert HyperVProvider().open_console("Lab VM")["ok"] is True
    argv = popen.call_args.args[0]
    assert argv[0].lower().endswith("vmconnect.exe") and argv[1:] == ["localhost", "Lab VM"]
