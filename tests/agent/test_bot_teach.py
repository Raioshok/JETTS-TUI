"""Teach a Jetts Bot by showing it once (agent/bot_teach.py + the teach RPCs)."""

from __future__ import annotations

import json
import time
from unittest.mock import patch

import pytest
from PIL import Image

from agent import bot_teach, bots


def _screens(*colors):
    """A capture function that walks through solid-colour screens, then stays on the last."""
    frames = [Image.new("RGB", (1920, 1080), c) for c in colors]
    state = {"i": 0}

    def capture():
        img = frames[min(state["i"], len(frames) - 1)]
        state["i"] += 1
        return img

    return capture


def _wait_frames(rec, n, timeout=5.0):
    end = time.time() + timeout
    while len(rec.frames) < n and time.time() < end:
        time.sleep(0.02)


@pytest.fixture(autouse=True)
def _bot():
    bots.create_bot("Scout", "Find talent")
    yield
    for bot_id in list(bot_teach._recordings):
        bot_teach.stop(bot_id)


def test_keeps_only_frames_that_changed_and_downscales_them():
    rec = bot_teach.start("scout", "Report", capture=_screens("white", "white", "black", "black", "white"),
                          interval=0.01)
    _wait_frames(rec, 3)
    time.sleep(0.1)
    rec = bot_teach.stop("scout")
    assert [f["file"] for f in rec.frames] == ["frame_001.png", "frame_002.png", "frame_003.png"]
    assert Image.open(rec.directory / "frame_001.png").size == (1280, 720)
    saved = json.loads((rec.directory / "frames.json").read_text(encoding="utf-8"))
    assert saved["title"] == "Report" and len(saved["frames"]) == 3


def test_frame_cap_ends_the_lesson_but_it_still_waits_for_stop_and_learn():
    colors = ["white", "black"] * 10
    rec = bot_teach.start("scout", "Report", capture=_screens(*colors), interval=0.01, max_frames=4)
    rec.thread.join(5)
    assert len(rec.frames) == 4
    assert bot_teach.is_watching("scout")
    bot_teach.stop("scout")
    assert not bot_teach.is_watching("scout")


def test_a_failing_capture_ends_the_lesson_with_its_error():
    def broken():
        raise RuntimeError("VM is off")

    rec = bot_teach.start("scout", "Report", capture=broken, interval=0.01)
    rec.thread.join(5)
    assert rec.error == "VM is off" and rec.frames == []


def test_start_is_validated_and_exclusive():
    with pytest.raises(ValueError):
        bot_teach.start("ghost", "x", capture=_screens("white"))
    with pytest.raises(ValueError):
        bot_teach.start("scout", "  ", capture=_screens("white"))
    bot_teach.start("scout", "x", capture=_screens("white"), interval=0.05)
    with pytest.raises(ValueError):
        bot_teach.start("scout", "again", capture=_screens("white"))
    bot_teach.stop("scout")
    with pytest.raises(ValueError):
        bot_teach.stop("scout")


def test_learn_prompt_points_at_the_frames_and_forbids_secrets():
    rec = bot_teach.start("scout", "Weekly Report", capture=_screens("white"), interval=0.01)
    _wait_frames(rec, 1)
    rec = bot_teach.stop("scout")
    prompt = bot_teach.learn_prompt(rec, "skip internal accounts")
    assert str(rec.directory) in prompt and "1 screenshot " in prompt
    assert "`scout-weekly-report`" in prompt and "skill_manage" in prompt and "vision_analyze" in prompt
    assert "Never" in prompt and "passwords" in prompt and "skip internal accounts" in prompt


class TestTeachRPCs:
    def test_stop_hands_the_recording_to_the_bot_as_a_task(self):
        from tui_gateway import server

        with patch("agent.bot_teach.capture_for", return_value=_screens("white", "black")):
            assert server._methods["bots.teach_start"]("r", {"id": "scout", "title": "Report"})["result"]["source"]
        _wait_frames(bot_teach._recordings["scout"], 2)
        assert server._methods["bots.list"]("r", {})["result"]["bots"][0]["watching"] is True
        tasks = []
        assign = lambda rid, p: tasks.append(p) or {"result": {"session_id": "live"}}
        with patch.dict(server._methods, {"bots.assign": assign}):
            res = server._methods["bots.teach_stop"]("r", {"id": "scout", "notes": "n"})
        assert res["result"]["frames"] >= 2
        assert tasks[0]["id"] == "scout" and "skill_manage" in tasks[0]["task"]

    def test_stop_with_nothing_recorded_does_not_bother_the_bot(self):
        from tui_gateway import server

        def broken():
            raise RuntimeError("VM is off")

        with patch("agent.bot_teach.capture_for", return_value=broken):
            server._methods["bots.teach_start"]("r", {"id": "scout", "title": "Report"})
        bot_teach._recordings["scout"].thread.join(5)
        with patch.dict(server._methods, {"bots.assign": lambda *a: pytest.fail("no lesson to learn")}):
            res = server._methods["bots.teach_stop"]("r", {"id": "scout"})
        assert res["error"]["message"] == "VM is off"
