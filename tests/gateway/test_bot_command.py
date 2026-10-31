"""/bot in messaging chats: talk to a Jetts Bot from Telegram, Discord, Slack…"""

from __future__ import annotations

import asyncio

import pytest

from agent import bots
from gateway.platforms.base import MessageEvent
from gateway.slash_commands import GatewaySlashCommandsMixin


class _Runner(GatewaySlashCommandsMixin):
    """Just the two runner methods /bot relies on."""

    def __init__(self):
        self.resets = []

    def _session_key_for_source(self, source):
        return "telegram:chat-1"

    async def _handle_reset_command(self, event):
        self.resets.append(event.text)
        return "New session started."


def _send(runner, text):
    return asyncio.run(runner._handle_bot_command(MessageEvent(text=text)))


@pytest.fixture
def runner():
    bots.create_bot("Research", "Dig up facts with sources")
    return _Runner()


def test_bare_bot_lists_the_roster_and_who_this_chat_talks_to(runner):
    reply = _send(runner, "/bot")
    assert "Research" in reply and "/bot research" in reply and "normal assistant" in reply
    assert runner.resets == []


def test_switching_binds_the_chat_and_starts_a_plain_new_session(runner):
    assert "now talking to Research" in _send(runner, "/bot research")
    assert bots.chat_bot("telegram:chat-1") == "research"
    assert runner.resets == ["/new"]  # never "/new research": that would title the session
    assert "Research" in _send(runner, "/bot")


def test_names_match_case_insensitively_and_unknown_bots_change_nothing(runner):
    _send(runner, "/bot RESEARCH")
    assert bots.chat_bot("telegram:chat-1") == "research"
    assert "No Bot named" in _send(runner, "/bot ghost")
    assert bots.chat_bot("telegram:chat-1") == "research"
    assert runner.resets == ["/new"]


def test_off_returns_to_the_normal_assistant(runner):
    assert "isn't talking to a Bot" in _send(runner, "/bot off")
    _send(runner, "/bot research")
    assert "Back to the normal assistant" in _send(runner, "/bot off")
    assert bots.chat_bot("telegram:chat-1") is None
    assert runner.resets == ["/new", "/new"]


def test_a_removed_bot_no_longer_answers_the_chat(runner):
    _send(runner, "/bot research")
    bots.remove_bot("research")
    assert bots.chat_bot("telegram:chat-1") is None
