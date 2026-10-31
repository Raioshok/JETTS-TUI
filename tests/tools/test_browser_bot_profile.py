"""Jetts Bots browse with one persistent profile so their web sign-ins last."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from tools import browser_native


def test_only_bot_sessions_get_the_shared_profile(tmp_path):
    with patch("agent.bots.bots_dir", return_value=tmp_path / "bots"), \
         patch("agent.bots.bot_for_session", side_effect=lambda s, db=None: "research" if s == "bot-s" else None), \
         patch("tools.approval.get_current_session_key", return_value="bot-s"):
        assert browser_native._bot_browser_profile() == tmp_path / "bots" / ".browser"
    with patch("agent.bots.bot_for_session", return_value=None), \
         patch("tools.approval.get_current_session_key", return_value="plain"):
        assert browser_native._bot_browser_profile() is None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows holds Chrome's lockfile open")
def test_a_profile_held_by_a_live_browser_is_in_use(tmp_path: Path):
    assert browser_native._profile_in_use(tmp_path) is False
    held = open(tmp_path / "lockfile", "w")
    try:
        assert browser_native._profile_in_use(tmp_path) is True
    finally:
        held.close()
    assert browser_native._profile_in_use(tmp_path) is False  # stale lock is cleared
    assert not (tmp_path / "lockfile").exists()


def test_in_use_profile_falls_back_to_a_throwaway(tmp_path: Path):
    with patch.object(browser_native, "_profile_in_use", return_value=True), \
         patch.object(browser_native, "find_browser_executable", return_value=None):
        with pytest.raises(browser_native.CDPError):  # no browser here; we only check the routing
            browser_native.launch_browser(session_name="s", headed=False, no_sandbox=False,
                                          persistent_profile=tmp_path / "shared")
    assert (tmp_path / "shared").is_dir()  # created, never deleted
