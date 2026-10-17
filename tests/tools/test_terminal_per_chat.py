"""Each chat gets its own local terminal; subagents share their parent's."""

import json

import pytest

import tools.terminal_tool as tt


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("TERMINAL_ENV", "local")
    monkeypatch.setattr(tt, "_active_environments", {})
    monkeypatch.setattr(tt, "_last_activity", {})
    monkeypatch.setattr(tt, "_task_env_overrides", {})
    monkeypatch.setattr(tt, "_session_cwd", {})
    monkeypatch.setattr(tt, "_task_parents", tt.OrderedDict())
    monkeypatch.setattr(tt, "_start_cleanup_thread", lambda: None)
    monkeypatch.setattr(tt, "_check_all_guards", lambda command, env_type, **kwargs: {"approved": True})
    yield tmp_path
    for env in list(tt._active_environments.values()):
        env.cleanup()


def run(task_id, command):
    return json.loads(tt.terminal_tool(command=command, task_id=task_id))["output"].strip()


def test_chats_do_not_share_exports_or_cwd(isolated):
    (isolated / "a").mkdir()
    (isolated / "b").mkdir()
    tt.register_task_env_overrides("chat-a", {"cwd": str(isolated / "a")})
    tt.register_task_env_overrides("chat-b", {"cwd": str(isolated / "b")})

    run("chat-a", "export ONLY_IN_A=1 && mkdir -p sub && cd sub")
    assert run("chat-b", "echo ${ONLY_IN_A:-unset}") == "unset"
    assert run("chat-a", "echo ${ONLY_IN_A:-unset}") == "1"
    assert run("chat-b", "basename \"$(pwd)\"") == "b"
    assert run("chat-a", "basename \"$(pwd)\"") == "sub"
    assert {"chat-a", "chat-b"} <= set(tt._active_environments)


def test_subagent_uses_its_parent_chats_terminal(isolated):
    tt.register_task_parent("subagent-1", "chat-a")
    tt.register_task_parent("subagent-1-child", "subagent-1")

    run("chat-a", "export FROM_PARENT=yes")
    assert run("subagent-1-child", "echo ${FROM_PARENT:-unset}") == "yes"
    assert tt._resolve_container_task_id("subagent-1-child") == "chat-a"


def test_per_turn_ids_and_remote_backends_share_the_default_terminal(isolated, monkeypatch):
    assert tt._resolve_container_task_id(f"{tt.EPHEMERAL_TASK_PREFIX}123") == "default"
    assert tt._resolve_container_task_id(None) == "default"

    monkeypatch.setenv("TERMINAL_ENV", "docker")
    assert tt._resolve_container_task_id("chat-a") == "default"


def test_a_chats_terminal_survives_end_of_turn_cleanup(isolated):
    run("chat-a", "export KEPT=1")
    assert tt.is_persistent_env("chat-a")
    assert run("chat-a", "echo ${KEPT:-unset}") == "1"
