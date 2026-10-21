"""Self-contained, coordinate-first computer-use backend.

The "modern" Claude/Codex-style path: a plain screenshot goes to the model,
the model replies with pixel coordinates, and we act on them. No external
binary — screenshots come from Pillow's ``ImageGrab`` and input is synthesized
natively (Windows ``SendInput`` via ctypes; ``pyautogui`` elsewhere when it is
installed; POSIX CLIs — ``xdotool`` / ``cliclick`` — as a last resort).

Two things make it behave like Anthropic's / OpenAI's reference computer tool:

1. **Screenshot downscaling.** A 4K frame tokenizes heavily and model click
   accuracy drops on huge images, so the screenshot handed to the model is
   downscaled so its longest edge is ``max_width`` (Anthropic recommends about
   1280px). ``_capture_response`` in ``tool.py`` derives the reported width /
   height from the PNG bytes, so the model always sees the scaled dimensions.

2. **Coordinate rescaling.** The model's ``[x, y]`` are in that *scaled* frame.
   Every action maps them back to real device pixels (``* self._scale_*``)
   before synthesizing input. This is exactly how the reference clients keep
   clicks landing after a downscale.

Differences from the cua-driver backend (intentional, documented in the skill):

* It moves the **real** cursor (foreground delivery). cua-driver's background,
  no-focus-steal delivery stays the reason to install it.
* There is no accessibility tree, so ``capture(mode='som'|'ax')`` degrades to a
  plain screenshot, ``elements`` is always empty, and there are no element
  indices — the model drives purely by coordinate.
"""

from __future__ import annotations

import base64
import io
import logging
import os
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from tools.computer_use.backend import (
    ActionResult,
    CaptureResult,
    ComputerUseBackend,
)

logger = logging.getLogger(__name__)

# Anthropic's reference clients target WXGA (~1280x800); accuracy falls off on
# larger frames and the token cost climbs. 0 disables downscaling.
_DEFAULT_MAX_WIDTH = 1280


def _display_present() -> bool:
    """True when this process can plausibly reach an interactive GUI."""
    try:
        if sys.platform == "win32":
            import ctypes

            # SM_CXSCREEN == 0 means no interactive desktop (e.g. a Session-0
            # service / headless SSH logon) — ImageGrab + SendInput are no-ops.
            return int(ctypes.windll.user32.GetSystemMetrics(0)) > 0
        if sys.platform == "darwin":
            return True
        # Linux / other X11: need a display server reachable.
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    except Exception:  # pragma: no cover - defensive
        return False


# ---------------------------------------------------------------------------
# Input engines — synthesize mouse / keyboard in DEVICE pixel coordinates.
# ---------------------------------------------------------------------------

_MODIFIER_ALIASES = {
    "cmd": "command", "super": "command", "win": "command", "windows": "command",
    "meta": "command", "option": "alt", "control": "ctrl",
}


def _norm_modifiers(mods: Optional[List[str]]) -> List[str]:
    out: List[str] = []
    for m in mods or []:
        m = (m or "").strip().lower()
        if not m:
            continue
        out.append(_MODIFIER_ALIASES.get(m, m))
    return out


class _InputEngine:
    """Device-pixel mouse/keyboard synthesis. Subclasses implement per-OS."""

    name = "base"

    def move(self, x: int, y: int) -> None: ...
    def click(self, x: int, y: int, button: str, count: int,
              modifiers: List[str]) -> None: ...
    def mouse_down(self, x: int, y: int, button: str) -> None: ...
    def mouse_up(self, x: int, y: int, button: str) -> None: ...
    def drag(self, x1: int, y1: int, x2: int, y2: int, button: str,
             modifiers: List[str]) -> None: ...
    def scroll(self, x: int, y: int, direction: str, amount: int) -> None: ...
    def type_text(self, text: str) -> None: ...
    def key(self, combo: str) -> None: ...
    def get_cursor_position(self) -> Tuple[int, int]:
        return 0, 0


# ── Windows: ctypes SendInput (no third-party dependency) ──────────────────

class _WindowsEngine(_InputEngine):
    name = "windows-sendinput"

    # Virtual-key codes for the names we accept in key combos (including Claude reference keynames).
    _VK = {
        "return": 0x0D, "enter": 0x0D, "tab": 0x09, "escape": 0x1B, "esc": 0x1B,
        "space": 0x20, "backspace": 0x08, "delete": 0x2E, "del": 0x2E,
        "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
        "page_up": 0x21, "page_down": 0x22,
        "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27, "insert": 0x2D,
        "ctrl": 0x11, "shift": 0x10, "alt": 0x12, "command": 0x5B, "win": 0x5B,
        "windows": 0x5B, "super": 0x5B, "meta": 0x5B, "super_l": 0x5B,
        "control_l": 0x11, "alt_l": 0x12, "shift_l": 0x10, "caps_lock": 0x14, "capslock": 0x14,
        "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
        "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    }

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        self._ct = ctypes
        self._wt = wintypes
        self._user32 = ctypes.windll.user32
        # Match screenshot pixels to SendInput's coordinate space on high-DPI
        # displays; without this a scaled desktop offsets every click.
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
        except Exception:
            try:
                self._user32.SetProcessDPIAware()
            except Exception:
                pass

        ULONG_PTR = ctypes.POINTER(wintypes.ULONG)

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                        ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("dwExtraInfo", ULONG_PTR)]

        class _INPUTunion(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("u", _INPUTunion)]

        self._MOUSEINPUT = MOUSEINPUT
        self._KEYBDINPUT = KEYBDINPUT
        self._INPUT = INPUT

    # -- low level ----------------------------------------------------------
    def _send(self, *inputs) -> None:
        n = len(inputs)
        arr = (self._INPUT * n)(*inputs)
        self._user32.SendInput(n, arr, self._ct.sizeof(self._INPUT))

    def _mk_mouse(self, flags: int, dx: int = 0, dy: int = 0, data: int = 0):
        inp = self._INPUT()
        inp.type = 0  # INPUT_MOUSE
        inp.u.mi = self._MOUSEINPUT(dx, dy, data, flags, 0, None)
        return inp

    def _mk_key(self, vk: int, up: bool = False):
        inp = self._INPUT()
        inp.type = 1  # INPUT_KEYBOARD
        inp.u.ki = self._KEYBDINPUT(vk, 0, 0x0002 if up else 0, 0, None)
        return inp

    def _mk_unicode(self, cp: int, up: bool = False):
        inp = self._INPUT()
        inp.type = 1
        flags = 0x0004 | (0x0002 if up else 0)  # KEYEVENTF_UNICODE [| KEYUP]
        inp.u.ki = self._KEYBDINPUT(0, cp, flags, 0, None)
        return inp

    def _abs(self, x: int, y: int) -> Tuple[int, int]:
        w = max(1, int(self._user32.GetSystemMetrics(0)) - 1)
        h = max(1, int(self._user32.GetSystemMetrics(1)) - 1)
        return round(x * 65535 / w), round(y * 65535 / h)

    _BTN = {
        "left": (0x0002, 0x0004), "right": (0x0008, 0x0010),
        "middle": (0x0020, 0x0040),
    }
    _MOVE_ABS = 0x0001 | 0x8000  # MOUSEEVENTF_MOVE | ABSOLUTE

    # -- engine API ---------------------------------------------------------
    def move(self, x: int, y: int) -> None:
        ax, ay = self._abs(x, y)
        self._send(self._mk_mouse(self._MOVE_ABS, ax, ay))

    def _press(self, mods: List[str]) -> List[int]:
        vks = [self._VK[m] for m in mods if m in self._VK]
        for vk in vks:
            self._send(self._mk_key(vk))
        return vks

    def _release(self, vks: List[int]) -> None:
        for vk in reversed(vks):
            self._send(self._mk_key(vk, up=True))

    def click(self, x, y, button, count, modifiers) -> None:
        down, up = self._BTN.get(button, self._BTN["left"])
        ax, ay = self._abs(x, y)
        self._send(self._mk_mouse(self._MOVE_ABS, ax, ay))
        held = self._press(_norm_modifiers(modifiers))
        for _ in range(max(1, count)):
            self._send(self._mk_mouse(down), self._mk_mouse(up))
            time.sleep(0.02)
        self._release(held)

    def mouse_down(self, x, y, button) -> None:
        down, _ = self._BTN.get(button, self._BTN["left"])
        ax, ay = self._abs(x, y)
        self._send(self._mk_mouse(self._MOVE_ABS, ax, ay), self._mk_mouse(down))

    def mouse_up(self, x, y, button) -> None:
        _, up = self._BTN.get(button, self._BTN["left"])
        ax, ay = self._abs(x, y)
        self._send(self._mk_mouse(self._MOVE_ABS, ax, ay), self._mk_mouse(up))

    def drag(self, x1, y1, x2, y2, button, modifiers) -> None:
        down, up = self._BTN.get(button, self._BTN["left"])
        held = self._press(_norm_modifiers(modifiers))
        a1 = self._abs(x1, y1)
        self._send(self._mk_mouse(self._MOVE_ABS, a1[0], a1[1]), self._mk_mouse(down))
        # A few intermediate moves so drag-aware targets register the motion.
        for i in range(1, 6):
            mx = round(x1 + (x2 - x1) * i / 5)
            my = round(y1 + (y2 - y1) * i / 5)
            amx, amy = self._abs(mx, my)
            self._send(self._mk_mouse(self._MOVE_ABS, amx, amy))
            time.sleep(0.01)
        self._send(self._mk_mouse(up))
        self._release(held)

    def scroll(self, x, y, direction, amount) -> None:
        ax, ay = self._abs(x, y)
        self._send(self._mk_mouse(self._MOVE_ABS, ax, ay))
        ticks = max(1, amount)
        if direction in ("up", "down"):
            delta = 120 * ticks * (1 if direction == "up" else -1)
            flag = 0x0800  # WHEEL
        else:
            delta = 120 * ticks * (1 if direction == "right" else -1)
            flag = 0x01000  # HWHEEL
        # mouseData is an unsigned DWORD; wrap negative wheel deltas.
        self._send(self._mk_mouse(flag, data=delta & 0xFFFFFFFF))

    def get_cursor_position(self) -> Tuple[int, int]:
        pt = self._wt.POINT()
        self._user32.GetCursorPos(self._ct.byref(pt))
        return int(pt.x), int(pt.y)

    def type_text(self, text: str) -> None:
        inputs = []
        for ch in text:
            for cu in ch.encode("utf-16-le").decode("utf-16-le"):
                cp = ord(cu)
                inputs.append(self._mk_unicode(cp))
                inputs.append(self._mk_unicode(cp, up=True))
        if inputs:
            self._send(*inputs)

    def key(self, combo: str) -> None:
        parts = [p.strip().lower() for p in combo.replace(" ", "").split("+") if p.strip()]
        parts = [_MODIFIER_ALIASES.get(p, p) for p in parts]
        if not parts:
            return
        *mods, final = parts
        held = self._press(mods)
        vk = self._VK.get(final)
        if vk is None and len(final) == 1:
            vk = self._user32.VkKeyScanW(ord(final)) & 0xFF
        if vk:
            self._send(self._mk_key(vk), self._mk_key(vk, up=True))
        self._release(held)


# ── pyautogui: cross-platform, used when installed ─────────────────────────

class _PyAutoGuiEngine(_InputEngine):
    name = "pyautogui"

    def __init__(self) -> None:
        import pyautogui  # noqa: F401

        self._p = pyautogui
        self._p.FAILSAFE = False
        self._p.PAUSE = 0.0

    def move(self, x, y) -> None:
        self._p.moveTo(x, y)

    def click(self, x, y, button, count, modifiers) -> None:
        mods = _norm_modifiers(modifiers)
        keymap = {"ctrl": "ctrl", "shift": "shift", "alt": "alt", "command": "command"}
        held = [keymap[m] for m in mods if m in keymap]
        for k in held:
            self._p.keyDown(k)
        try:
            self._p.click(x=x, y=y, clicks=max(1, count),
                          button={"left": "left", "right": "right", "middle": "middle"}.get(button, "left"),
                          interval=0.02)
        finally:
            for k in reversed(held):
                self._p.keyUp(k)

    def mouse_down(self, x, y, button) -> None:
        self._p.mouseDown(x=x, y=y, button=button)

    def mouse_up(self, x, y, button) -> None:
        self._p.mouseUp(x=x, y=y, button=button)

    def drag(self, x1, y1, x2, y2, button, modifiers) -> None:
        self._p.moveTo(x1, y1)
        self._p.dragTo(x2, y2, button=button, duration=0.2)

    def scroll(self, x, y, direction, amount) -> None:
        self._p.moveTo(x, y)
        ticks = max(1, amount) * 100
        if direction in ("up", "down"):
            self._p.scroll(ticks if direction == "up" else -ticks)
        else:
            self._p.hscroll(ticks if direction == "right" else -ticks)

    def type_text(self, text: str) -> None:
        self._p.typewrite(text, interval=0.005)

    def key(self, combo: str) -> None:
        parts = [p.strip().lower() for p in combo.replace(" ", "").split("+") if p.strip()]
        parts = [_MODIFIER_ALIASES.get(p, p) for p in parts]
        parts = ["enter" if p == "return" else p for p in parts]
        if len(parts) == 1:
            self._p.press(parts[0])
        elif parts:
            self._p.hotkey(*parts)

    def get_cursor_position(self) -> Tuple[int, int]:
        pos = self._p.position()
        return int(pos[0]), int(pos[1])


# ── POSIX CLI fallback: xdotool (Linux) / cliclick (macOS) ─────────────────

class _PosixCliEngine(_InputEngine):
    name = "posix-cli"

    def __init__(self) -> None:
        self._xdotool = shutil.which("xdotool")
        self._cliclick = shutil.which("cliclick")
        if not (self._xdotool or self._cliclick):
            raise RuntimeError("no xdotool/cliclick on PATH")

    def _run(self, *args: str) -> None:
        subprocess.run(list(args), check=False, timeout=15, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def move(self, x, y) -> None:
        if self._xdotool:
            self._run(self._xdotool, "mousemove", str(x), str(y))
        elif self._cliclick:
            self._run(self._cliclick, f"m:{x},{y}")

    def click(self, x, y, button, count, modifiers) -> None:
        self.move(x, y)
        btn = {"left": "1", "right": "3", "middle": "2"}.get(button, "1")
        if self._xdotool:
            for _ in range(max(1, count)):
                self._run(self._xdotool, "click", btn)
        elif self._cliclick:
            verb = "dc" if count >= 2 else "c"
            self._run(self._cliclick, f"{verb}:{x},{y}")

    def mouse_down(self, x, y, button) -> None:
        self.move(x, y)
        if self._xdotool:
            self._run(self._xdotool, "mousedown", {"left": "1", "right": "3", "middle": "2"}.get(button, "1"))

    def mouse_up(self, x, y, button) -> None:
        self.move(x, y)
        if self._xdotool:
            self._run(self._xdotool, "mouseup", {"left": "1", "right": "3", "middle": "2"}.get(button, "1"))

    def drag(self, x1, y1, x2, y2, button, modifiers) -> None:
        btn = {"left": "1", "right": "3", "middle": "2"}.get(button, "1")
        if self._xdotool:
            self.move(x1, y1)
            self._run(self._xdotool, "mousedown", btn)
            self.move(x2, y2)
            self._run(self._xdotool, "mouseup", btn)
        elif self._cliclick:
            self._run(self._cliclick, f"dd:{x1},{y1}", f"du:{x2},{y2}")

    def scroll(self, x, y, direction, amount) -> None:
        self.move(x, y)
        if self._xdotool:
            btn = {"up": "4", "down": "5", "left": "6", "right": "7"}.get(direction, "5")
            for _ in range(max(1, amount)):
                self._run(self._xdotool, "click", btn)

    def type_text(self, text: str) -> None:
        if self._xdotool:
            self._run(self._xdotool, "type", "--clearmodifiers", text)
        elif self._cliclick:
            self._run(self._cliclick, f"t:{text}")

    def key(self, combo: str) -> None:
        parts = [p.strip().lower() for p in combo.replace(" ", "").split("+") if p.strip()]
        if self._xdotool:
            xmap = {"ctrl": "ctrl", "alt": "alt", "shift": "shift", "command": "super",
                    "return": "Return", "enter": "Return", "escape": "Escape",
                    "tab": "Tab", "space": "space"}
            keyseq = "+".join(xmap.get(p, p) for p in parts)
            self._run(self._xdotool, "key", "--clearmodifiers", keyseq)

    def get_cursor_position(self) -> Tuple[int, int]:
        if self._xdotool:
            try:
                proc = subprocess.run(
                    [self._xdotool, "getmouselocation", "--shell"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    stdin=subprocess.DEVNULL,
                    timeout=2,
                )
                x, y = 0, 0
                for line in proc.stdout.splitlines():
                    if line.startswith("X="):
                        x = int(line.split("=")[1])
                    elif line.startswith("Y="):
                        y = int(line.split("=")[1])
                return x, y
            except Exception:
                pass
        return 0, 0


def _resolve_engine() -> _InputEngine:
    """Pick the best input engine available on this host.

    pyautogui first when installed (one proven code path for all three OSes),
    then the dependency-free Windows ctypes engine, then POSIX CLIs.
    """
    try:
        return _PyAutoGuiEngine()
    except Exception:
        pass
    if sys.platform == "win32":
        return _WindowsEngine()
    return _PosixCliEngine()


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------

class NativeBackend(ComputerUseBackend):
    """Coordinate-first, zero-external-binary computer-use backend."""

    def __init__(self, max_width: Optional[int] = None) -> None:
        self._engine: Optional[_InputEngine] = None
        self._max_width = _DEFAULT_MAX_WIDTH if max_width is None else int(max_width)
        # Scale factor: device_px = scaled_px * scale. 1.0 until first capture.
        self._scale_x = 1.0
        self._scale_y = 1.0

    # -- lifecycle ----------------------------------------------------------
    def start(self) -> None:
        if self._engine is None:
            self._engine = _resolve_engine()

    def stop(self) -> None:
        self._engine = None

    def is_available(self) -> bool:
        if sys.platform not in ("win32", "darwin", "linux"):
            return False
        if not _display_present():
            return False
        try:
            from PIL import ImageGrab  # noqa: F401
        except Exception:
            return False
        try:
            _resolve_engine()
            return True
        except Exception:
            return False

    # -- helpers ------------------------------------------------------------
    def _grab(self):
        from PIL import ImageGrab

        img = ImageGrab.grab()
        return img.convert("RGB")

    def _to_device(self, x: Optional[int], y: Optional[int]) -> Tuple[int, int]:
        """Map model (scaled-frame) coordinates back to real device pixels."""
        xi = int(round((x or 0) * self._scale_x))
        yi = int(round((y or 0) * self._scale_y))
        return xi, yi

    def _eng(self) -> _InputEngine:
        if self._engine is None:
            self.start()
        assert self._engine is not None
        return self._engine

    @staticmethod
    def _coord_required(x, y, label: str) -> Optional[ActionResult]:
        if x is None or y is None:
            return ActionResult(
                ok=False, action=label,
                message="native backend needs a coordinate=[x,y]; it has no "
                        "element indices (install cua-driver for element/SOM).",
                effect="suspected_noop", code="element_unsupported",
            )
        return None

    # -- capture ------------------------------------------------------------
    def capture(self, mode: str = "som", app: Optional[str] = None,
                pid: Optional[int] = None, window_id: Optional[int] = None) -> CaptureResult:
        img = self._grab()
        nat_w, nat_h = img.size
        out = img

        # Match Anthropic Claude computer use standard scaling targets when max_width is not explicitly capping below:
        ratio = nat_w / nat_h if nat_h else 1.0
        target_w, target_h = None, None
        if self._max_width and nat_w > self._max_width:
            target_w = self._max_width
            target_h = max(1, round(nat_h * (target_w / nat_w)))
        elif not self._max_width:
            # Claude standard targets: FWXGA (~16:9, 1366x768), WXGA (16:10, 1280x800), XGA (4:3, 1024x768)
            if abs(16 / 9 - ratio) < 0.15 and nat_w > 1366:
                target_w, target_h = 1366, 768
            elif abs(16 / 10 - ratio) < 0.15 and nat_w > 1280:
                target_w, target_h = 1280, 800
            elif abs(4 / 3 - ratio) < 0.15 and nat_w > 1024:
                target_w, target_h = 1024, 768

        if target_w and target_h:
            out = img.resize((target_w, target_h))

        scaled_w, scaled_h = out.size
        # Record the mapping for subsequent coordinate actions.
        self._scale_x = nat_w / scaled_w if scaled_w else 1.0
        self._scale_y = nat_h / scaled_h if scaled_h else 1.0

        # Fast PNG compression (level 1) cuts encoding time by ~2.5x without visual degradation
        buf = io.BytesIO()
        out.save(buf, format="PNG", compress_level=1)
        raw = buf.getvalue()
        return CaptureResult(
            mode="vision",  # native has no AX tree; som/ax degrade to pixels
            width=scaled_w, height=scaled_h,
            png_b64=base64.b64encode(raw).decode("ascii"),
            elements=[], app=app or "", window_title="",
            png_bytes_len=len(raw), image_mime_type="image/png",
        )

    # -- pointer ------------------------------------------------------------
    def mouse_move(self, *, x: Optional[int] = None, y: Optional[int] = None, **kwargs) -> ActionResult:
        bad = self._coord_required(x, y, "mouse_move")
        if bad:
            return bad
        dx, dy = self._to_device(x, y)
        self._eng().move(dx, dy)
        return ActionResult(
            ok=True, action="mouse_move", path=f"native_{self._eng().name}",
            effect="unverifiable", delivery_mode="foreground",
            message=f"moved mouse to ({x},{y}) [device ({dx},{dy})]",
            meta={"x": x, "y": y, "device_x": dx, "device_y": dy},
        )

    def mouse_down(self, *, x: Optional[int] = None, y: Optional[int] = None, button: str = "left", **kwargs) -> ActionResult:
        if x is not None and y is not None:
            dx, dy = self._to_device(x, y)
            self._eng().move(dx, dy)
        else:
            dx, dy = self._eng().get_cursor_position()
        self._eng().mouse_down(dx, dy, button)
        return ActionResult(
            ok=True, action="mouse_down", path=f"native_{self._eng().name}",
            effect="unverifiable", delivery_mode="foreground",
            message=f"mouse_down {button}",
        )

    def mouse_up(self, *, x: Optional[int] = None, y: Optional[int] = None, button: str = "left", **kwargs) -> ActionResult:
        if x is not None and y is not None:
            dx, dy = self._to_device(x, y)
            self._eng().move(dx, dy)
        else:
            dx, dy = self._eng().get_cursor_position()
        self._eng().mouse_up(dx, dy, button)
        return ActionResult(
            ok=True, action="mouse_up", path=f"native_{self._eng().name}",
            effect="unverifiable", delivery_mode="foreground",
            message=f"mouse_up {button}",
        )

    def cursor_position(self) -> ActionResult:
        try:
            dx, dy = self._eng().get_cursor_position()
            sx = int(round(dx / self._scale_x)) if self._scale_x else dx
            sy = int(round(dy / self._scale_y)) if self._scale_y else dy
            return ActionResult(
                ok=True, action="cursor_position", path=f"native_{self._eng().name}",
                effect="confirmed", delivery_mode="background",
                message=f"X={sx},Y={sy}",
                meta={"x": sx, "y": sy, "coordinate": [sx, sy], "device_x": dx, "device_y": dy, "output": f"X={sx},Y={sy}"},
            )
        except Exception as e:
            return ActionResult(ok=False, action="cursor_position", message=str(e))

    def triple_click(self, *, x: Optional[int] = None, y: Optional[int] = None, button: str = "left",
                     modifiers: Optional[List[str]] = None, **kwargs) -> ActionResult:
        return self.click(x=x, y=y, button=button, click_count=3, modifiers=modifiers, **kwargs)
    def click(self, *, element=None, x=None, y=None, button="left", click_count=1,
              modifiers=None, delivery_mode=None, bring_to_front=False) -> ActionResult:
        if element is not None and x is None and y is None:
            return self._coord_required(None, None, "click")
        bad = self._coord_required(x, y, "click")
        if bad:
            return bad
        dx, dy = self._to_device(x, y)
        self._eng().click(dx, dy, button, click_count, modifiers or [])
        return ActionResult(
            ok=True, action="click", path=f"native_{self._eng().name}",
            effect="unverifiable", delivery_mode="foreground",
            message=f"clicked ({x},{y}) [device ({dx},{dy})]; re-capture to verify.",
        )

    def drag(self, *, from_element=None, to_element=None, from_xy=None, to_xy=None,
             button="left", modifiers=None, delivery_mode=None, bring_to_front=False) -> ActionResult:
        if not from_xy or not to_xy:
            return ActionResult(
                ok=False, action="drag",
                message="native backend needs from_coordinate/to_coordinate.",
                effect="suspected_noop", code="element_unsupported",
            )
        x1, y1 = self._to_device(from_xy[0], from_xy[1])
        x2, y2 = self._to_device(to_xy[0], to_xy[1])
        self._eng().drag(x1, y1, x2, y2, button, modifiers or [])
        return ActionResult(ok=True, action="drag", effect="unverifiable",
                            delivery_mode="foreground", path=f"native_{self._eng().name}")

    def scroll(self, *, direction, amount=3, element=None, x=None, y=None,
               modifiers=None, delivery_mode=None, bring_to_front=False) -> ActionResult:
        # Scroll at the given point, or (0,0) when the model gives no coordinate
        # (engines scroll the window under the pointer / focused control).
        if x is None or y is None:
            dx, dy = 0, 0
        else:
            dx, dy = self._to_device(x, y)
        self._eng().scroll(dx, dy, direction, int(amount))
        return ActionResult(ok=True, action="scroll", effect="unverifiable",
                            delivery_mode="foreground", path=f"native_{self._eng().name}")

    # -- keyboard -----------------------------------------------------------
    def type_text(self, text, *, delivery_mode=None, bring_to_front=False) -> ActionResult:
        self._eng().type_text(text)
        return ActionResult(ok=True, action="type", effect="unverifiable",
                            delivery_mode="foreground", path=f"native_{self._eng().name}")

    def key(self, keys, *, delivery_mode=None, bring_to_front=False) -> ActionResult:
        self._eng().key(keys)
        return ActionResult(ok=True, action="key", effect="unverifiable",
                            delivery_mode="foreground", path=f"native_{self._eng().name}")

    # -- introspection ------------------------------------------------------
    def list_apps(self) -> List[Dict[str, Any]]:
        if sys.platform == "win32":
            try:
                return self._list_windows_win()
            except Exception as e:  # pragma: no cover - defensive
                logger.debug("native list_apps failed: %s", e)
        return []

    def list_windows(self) -> List[Dict[str, Any]]:
        return self.list_apps()

    def _list_windows_win(self) -> List[Dict[str, Any]]:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        out: List[Dict[str, Any]] = []
        EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def _cb(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.strip()
            if not title:
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            out.append({"title": title, "pid": int(pid.value), "window_id": int(hwnd)})
            return True

        user32.EnumWindows(EnumProc(_cb), 0)
        return out

    def focus_app(self, app: str, raise_window: bool = False) -> ActionResult:
        if sys.platform == "win32":
            try:
                import ctypes

                user32 = ctypes.windll.user32
                target = (app or "").lower()
                for w in self._list_windows_win():
                    if target in w["title"].lower():
                        user32.SetForegroundWindow(w["window_id"])
                        return ActionResult(ok=True, action="focus_app",
                                            message=f"fronted {w['title']!r}")
                return ActionResult(ok=False, action="focus_app",
                                    message=f"no visible window matching {app!r}")
            except Exception as e:  # pragma: no cover - defensive
                return ActionResult(ok=False, action="focus_app", message=str(e))
        return ActionResult(ok=False, action="focus_app", code="unsupported",
                            message="focus_app needs cua-driver on this platform.")

    def set_value(self, value: str, element: Optional[int] = None) -> ActionResult:
        return ActionResult(
            ok=False, action="set_value", code="element_unsupported",
            message="set_value needs the accessibility tree — install cua-driver, "
                    "or click the control and type.",
        )
