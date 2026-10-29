"""Teach a Jetts Bot a task by showing it once.

While the user does a workflow, a recorder screenshots the Bots' computer (or
the user's screen when the Bots have none) and keeps only frames that changed.
Screenshots only — never keystrokes, so typed passwords are not captured.
When the user stops, the frames go to the Bot as a task: it studies them with
its own vision tool and saves a skill it can follow next time (see
``learn_prompt``). Lessons live in ``bots/<id>/lessons/<stamp>/`` and are
archived with the Bot.
"""

from __future__ import annotations

import io
import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PIL import Image, ImageChops, ImageStat

INTERVAL_SECONDS = 2.0
MAX_FRAMES = 120
MAX_SECONDS = 15 * 60
# Mean per-pixel change (0-255) on a small grayscale thumbnail that counts as a new step.
CHANGE_THRESHOLD = 3.0
_THUMB = (96, 54)
_MAX_WIDTH = 1280

Capture = Callable[[], Image.Image]


@dataclass
class Recording:
    bot_id: str
    title: str
    source: str  # VM name, or "your screen"
    directory: Path
    started_at: float = field(default_factory=time.time)
    frames: List[Dict[str, Any]] = field(default_factory=list)
    stop_event: threading.Event = field(default_factory=threading.Event)
    thread: Optional[threading.Thread] = None
    error: Optional[str] = None


_recordings: Dict[str, Recording] = {}
_lock = threading.Lock()


def _changed(prev: Optional[Image.Image], img: Image.Image) -> bool:
    if prev is None:
        return True
    a = prev.convert("L").resize(_THUMB)
    b = img.convert("L").resize(_THUMB)
    return ImageStat.Stat(ImageChops.difference(a, b)).mean[0] >= CHANGE_THRESHOLD


def _record(rec: Recording, capture: Capture, interval: float, max_frames: int, max_seconds: float) -> None:
    last: Optional[Image.Image] = None
    while not rec.stop_event.is_set():
        if time.time() - rec.started_at > max_seconds or len(rec.frames) >= max_frames:
            break
        try:
            img = capture()
        except Exception as exc:  # a VM that stops mid-lesson ends the lesson, not the backend
            rec.error = str(exc)
            break
        if _changed(last, img):
            if img.width > _MAX_WIDTH:
                img = img.resize((_MAX_WIDTH, round(img.height * _MAX_WIDTH / img.width)))
            name = f"frame_{len(rec.frames) + 1:03d}.png"
            img.save(rec.directory / name, format="PNG", compress_level=1)
            rec.frames.append({"file": name, "seconds": round(time.time() - rec.started_at, 1)})
            last = img
        rec.stop_event.wait(interval)
    (rec.directory / "frames.json").write_text(
        json.dumps({"title": rec.title, "source": rec.source, "frames": rec.frames}, indent=2),
        encoding="utf-8",
    )


def capture_for(computer: Optional[str]) -> Capture:
    """Screenshot the Bots' computer, or the user's screen when there is none."""
    if computer:
        from tools.computer_use.vm_manager import get_vm_manager

        def from_vm() -> Image.Image:
            import base64

            b64, err, _w, _h = get_vm_manager().capture_screen(computer, max_width=_MAX_WIDTH)
            if err or not b64:
                raise RuntimeError(err or f"could not capture {computer}")
            return Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")

        return from_vm

    def from_screen() -> Image.Image:
        from PIL import ImageGrab

        return ImageGrab.grab().convert("RGB")

    return from_screen


def start(bot_id: str, title: str, *, capture: Optional[Capture] = None,
          interval: float = INTERVAL_SECONDS, max_frames: int = MAX_FRAMES,
          max_seconds: float = MAX_SECONDS) -> Recording:
    from agent import bots

    bot = bots.get_bot(bot_id)
    if bot is None:
        raise ValueError(f"no bot named {bot_id!r}")
    title = (title or "").strip()
    if not title:
        raise ValueError("say what you are about to show")
    computer = bots.bot_computer()
    with _lock:
        if bot_id in _recordings and not _recordings[bot_id].stop_event.is_set():
            raise ValueError(f"{bot['name']} is already watching")
        directory = bots.bots_dir() / bot_id / "lessons" / time.strftime("%Y%m%d-%H%M%S")
        directory.mkdir(parents=True, exist_ok=True)
        rec = Recording(bot_id=bot_id, title=title, source=computer or "your screen", directory=directory)
        rec.thread = threading.Thread(
            target=_record,
            args=(rec, capture or capture_for(computer), interval, max_frames, max_seconds),
            daemon=True, name=f"bot-teach-{bot_id}",
        )
        _recordings[bot_id] = rec
    rec.thread.start()
    return rec


def is_watching(bot_id: str) -> bool:
    """True from start until the user stops, even if the lesson hit its cap."""
    with _lock:
        return bot_id in _recordings


def stop(bot_id: str) -> Recording:
    with _lock:
        rec = _recordings.pop(bot_id, None)
    if rec is None:
        raise ValueError("this Bot is not watching")
    rec.stop_event.set()
    if rec.thread is not None:
        rec.thread.join(timeout=30)
    return rec


def learn_prompt(rec: Recording, notes: str = "") -> str:
    """The task that turns a recording into a skill, done by the Bot itself."""
    from agent.bots import slugify

    skill = f"{rec.bot_id}-{slugify(rec.title) or 'task'}"[:64].rstrip("-")
    note_line = f"\nMy notes: {notes.strip()}" if notes.strip() else ""
    return (
        f"I just showed you how to do this on {rec.source}: {rec.title}.{note_line}\n"
        f"The recording is {len(rec.frames)} screenshot{'s' if len(rec.frames) != 1 else ''} "
        f"in order in {rec.directory} "
        "(frame_001.png onward; frames.json has the seconds each was taken). Study them "
        "with vision_analyze, skipping near-duplicates, then save a reusable skill named "
        f"`{skill}` with skill_manage whose steps let you do this yourself next time with "
        "computer_use on your computer. Describe each control by what it looks like and "
        "what it says, not by pixel position, and say how to check each step worked. Never "
        "write passwords, keys or other secrets into the skill; where a step needs a "
        "sign-in, say to ask me. When it's saved, tell me the skill name and the steps in short."
    )
