"""Tests for the self-contained, coordinate-first native computer-use backend.

No real GUI is driven: the screen grab is stubbed with a Pillow image and the
input engine is a recorder. These assert the behaviour contracts that matter —
screenshot downscaling, model→device coordinate rescaling, coordinate-only
semantics, availability gating, and backend selection — not pixel plumbing.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from PIL import Image

from tools.computer_use import native_backend as nbmod
from tools.computer_use.native_backend import NativeBackend


class _RecordingEngine(nbmod._InputEngine):
    name = "recorder"

    def __init__(self) -> None:
        self.calls = []

    def move(self, x, y):
        self.calls.append(("move", x, y))

    def click(self, x, y, button, count, modifiers):
        self.calls.append(("click", x, y, button, count, tuple(modifiers)))

    def drag(self, x1, y1, x2, y2, button, modifiers):
        self.calls.append(("drag", x1, y1, x2, y2, button))

    def scroll(self, x, y, direction, amount):
        self.calls.append(("scroll", x, y, direction, amount))

    def type_text(self, text):
        self.calls.append(("type", text))

    def key(self, combo):
        self.calls.append(("key", combo))


def _backend_with(engine, image_size=(1920, 1080), max_width=1280):
    b = NativeBackend(max_width=max_width)
    b._engine = engine
    # Stub the screen grab so no display is needed.
    b._grab = lambda: Image.new("RGB", image_size, (10, 20, 30))  # type: ignore[assignment]
    return b


def test_capture_downscales_to_max_width_and_records_scale():
    eng = _RecordingEngine()
    b = _backend_with(eng, image_size=(1920, 1080), max_width=1280)

    cap = b.capture(mode="vision")

    # Screenshot handed to the model is downscaled to the 1280 longest edge.
    assert cap.width == 1280
    assert cap.height == 720
    assert cap.png_b64 and cap.mode == "vision"
    # Scale is native/scaled so coordinates map back up.
    assert b._scale_x == pytest.approx(1920 / 1280)
    assert b._scale_y == pytest.approx(1080 / 720)


def test_click_rescales_model_coordinates_to_device_pixels():
    eng = _RecordingEngine()
    b = _backend_with(eng, image_size=(1920, 1080), max_width=1280)
    b.capture(mode="vision")  # sets the scale

    res = b.click(x=640, y=360, button="left", click_count=1)

    assert res.ok
    # 640,360 in the 1280x720 frame → 960,540 device pixels.
    assert ("click", 960, 540, "left", 1, ()) == eng.calls[-1]
    assert res.delivery_mode == "foreground"


def test_no_downscale_keeps_coordinates_one_to_one():
    eng = _RecordingEngine()
    b = _backend_with(eng, image_size=(1000, 800), max_width=0)

    cap = b.capture(mode="vision")
    assert (cap.width, cap.height) == (1000, 800)

    b.click(x=123, y=456)
    assert eng.calls[-1] == ("click", 123, 456, "left", 1, ())


def test_som_capture_degrades_to_plain_screenshot_no_elements():
    eng = _RecordingEngine()
    b = _backend_with(eng)
    cap = b.capture(mode="som")
    # Native has no accessibility tree → always a plain vision capture.
    assert cap.mode == "vision"
    assert cap.elements == []


def test_click_by_element_is_rejected_as_unsupported():
    eng = _RecordingEngine()
    b = _backend_with(eng)
    res = b.click(element=7)
    assert not res.ok
    assert res.code == "element_unsupported"
    assert not eng.calls  # nothing synthesized


def test_set_value_and_coordinateless_click_are_rejected():
    eng = _RecordingEngine()
    b = _backend_with(eng)
    assert b.set_value("Blue").code == "element_unsupported"
    assert b.click().code == "element_unsupported"


def test_drag_rescales_both_endpoints():
    eng = _RecordingEngine()
    b = _backend_with(eng, image_size=(1920, 1080), max_width=1280)
    b.capture(mode="vision")
    b.drag(from_xy=(100, 100), to_xy=(200, 200))
    assert eng.calls[-1] == ("drag", 150, 150, 300, 300, "left")


def test_is_available_requires_display_and_engine():
    b = NativeBackend()
    with patch.object(nbmod, "_display_present", return_value=False):
        assert b.is_available() is False
    with patch.object(nbmod, "_display_present", return_value=True), \
         patch.object(nbmod, "_resolve_engine", return_value=_RecordingEngine()):
        assert b.is_available() is True


def test_resolve_backend_name_auto_prefers_cua_when_installed():
    from tools.computer_use import tool as cu_tool

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("JETTSTUI_COMPUTER_USE_BACKEND", None)
        with patch.object(cu_tool, "_computer_use_config", return_value={"backend": "auto"}):
            with patch("tools.computer_use.cua_backend.cua_driver_binary_available",
                       return_value=True):
                assert cu_tool._resolve_backend_name() == "cua"
            with patch("tools.computer_use.cua_backend.cua_driver_binary_available",
                       return_value=False):
                assert cu_tool._resolve_backend_name() == "native"


def test_resolve_backend_name_env_override_wins():
    from tools.computer_use import tool as cu_tool

    with patch.dict(os.environ, {"JETTSTUI_COMPUTER_USE_BACKEND": "native"}, clear=False):
        assert cu_tool._resolve_backend_name() == "native"


def test_check_requirements_true_for_native_when_available():
    from tools.computer_use import tool as cu_tool

    with patch.object(cu_tool, "_resolve_backend_name", return_value="native"), \
         patch.object(NativeBackend, "is_available", return_value=True):
        assert cu_tool.check_computer_use_requirements() is True
    with patch.object(cu_tool, "_resolve_backend_name", return_value="native"), \
         patch.object(NativeBackend, "is_available", return_value=False):
        assert cu_tool.check_computer_use_requirements() is False
