"""Safety contracts for computer_use: approval on every surface, no input replay,
vm_exec guards, unattended scoping, and native-backend input correctness."""

from __future__ import annotations

import json
import os
import re
import sys
import threading
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from tools.computer_use import tool as cu
from tools.computer_use.backend import CaptureResult, UIElement


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path):
    import tools.computer_use.vm_manager as vmm

    cu.reset_backend_for_tests()
    cu.set_approval_callback(None)
    with patch("tools.computer_use.vm_manager.VMManager._default_storage_path",
               return_value=tmp_path / "vms.json"), \
         patch.dict(os.environ, {"JETTSTUI_COMPUTER_USE_BACKEND": "noop"}, clear=False):
        vmm._global_vm_manager = None
        yield
        vmm._global_vm_manager = None
    cu.set_approval_callback(None)
    cu.reset_backend_for_tests()


def _backend_calls():
    return [name for name, _ in cu._get_backend().calls]


class TestApprovalGate:
    def test_no_callback_and_no_human_fails_closed(self, monkeypatch):
        for var in ("JETTSTUI_INTERACTIVE", "JETTSTUI_GATEWAY_SESSION", "JETTSTUI_CRON_SESSION",
                    "JETTSTUI_YOLO_MODE"):
            monkeypatch.delenv(var, raising=False)
        res = json.loads(cu.handle_computer_use({"action": "click", "coordinate": [1, 2]}))
        assert "error" in res
        assert "click" not in _backend_calls()

    def test_no_callback_uses_shared_gate_scoped_by_target(self):
        with patch("tools.approval.request_tool_approval", return_value={"approved": True}) as gate:
            cu.handle_computer_use({"action": "type", "text": "hi"})
        assert gate.call_args.args[0] == "computer_use"
        assert gate.call_args.kwargs["rule_key"] == "computer_use:type:background:host"

    def test_shared_gate_denial_blocks_action(self):
        with patch("tools.approval.request_tool_approval",
                   return_value={"approved": False, "message": "BLOCKED: no"}):
            res = json.loads(cu.handle_computer_use({"action": "key", "keys": "ctrl+s"}))
        assert res["error"] == "BLOCKED: no"
        assert "key" not in _backend_calls()

    def test_session_approval_for_a_vm_does_not_cover_the_host(self):
        from tools.computer_use.vm_manager import get_vm_manager

        get_vm_manager().register_vm("lab", vm_type="vps_ssh", os_type="linux", host="10.0.0.9")
        prompts = []

        def cb(action, args, summary):
            prompts.append(summary)
            return "approve_session"

        cu.set_approval_callback(cb)
        with patch("tools.computer_use.vm_manager.RemoteVPSProvider.send_input", return_value={"ok": True}):
            cu.handle_computer_use({"action": "click", "coordinate": [1, 2], "target": "lab"})
            cu.handle_computer_use({"action": "click", "coordinate": [3, 4], "target": "lab"})
        cu.handle_computer_use({"action": "click", "coordinate": [5, 6]})
        assert len(prompts) == 2
        assert "'lab'" in prompts[0] and "'lab'" not in prompts[1]

    def test_unknown_action_is_rejected_before_any_gate(self):
        cb = MagicMock(return_value="approve_once")
        cu.set_approval_callback(cb)
        res = json.loads(cu.handle_computer_use({"action": "format_disk"}))
        assert "unknown action" in res["error"]
        cb.assert_not_called()


class TestVmExecGuard:
    def test_hardline_command_is_blocked_before_approval(self):
        cb = MagicMock(return_value="approve_once")
        cu.set_approval_callback(cb)
        with patch("tools.computer_use.vm_manager.VMManager.execute_in_vm") as run:
            res = json.loads(cu.handle_computer_use(
                {"action": "vm_exec", "vm_name": "Ubuntu", "command": "rm -rf /"}))
        assert "error" in res
        run.assert_not_called()
        cb.assert_not_called()

    def test_plain_command_still_needs_vm_exec_approval(self):
        cb = MagicMock(return_value="deny")
        cu.set_approval_callback(cb)
        res = json.loads(cu.handle_computer_use(
            {"action": "vm_exec", "vm_name": "Ubuntu", "command": "uname -a"}))
        assert res["error"] == "denied by user"
        cb.assert_called_once()


class TestNoInputReplay:
    def _session(self, error: Exception):
        from tools.computer_use.cua_backend import _CuaDriverSession

        class Bridge:
            calls = 0

            def run(self, value, timeout=None):
                Bridge.calls += 1
                raise error

        session = cast(Any, _CuaDriverSession.__new__(_CuaDriverSession))
        session._bridge = Bridge()
        session._lock = threading.Lock()
        session._started = True
        session._call_tool_async = lambda name, args: (name, args)
        session._restart_session_locked = MagicMock()
        session._call_tool_via_cli = MagicMock(return_value={"isError": False})
        return session, Bridge

    def test_transient_error_on_input_is_not_retried(self):
        eagain = RuntimeError("Resource temporarily unavailable (os error 35)")
        session, bridge = self._session(eagain)
        with pytest.raises(RuntimeError):
            session.call_tool("click", {"x": 1})
        session._call_tool_via_cli.assert_not_called()
        assert bridge.calls == 1

    def test_closed_session_on_input_reconnects_without_replaying(self):
        session, bridge = self._session(BrokenPipeError())
        with pytest.raises(BrokenPipeError):
            session.call_tool("type_text", {"text": "x"})
        session._restart_session_locked.assert_called_once()
        assert bridge.calls == 1

    def test_read_only_call_still_falls_back_to_cli(self):
        eagain = RuntimeError("Resource temporarily unavailable (os error 35)")
        session, _ = self._session(eagain)
        session.call_tool("get_window_state", {})
        session._call_tool_via_cli.assert_called_once()


class TestUnattendedScope:
    def test_model_set_mode_is_not_persisted(self, tmp_path: Path):
        from tools.computer_use.vm_manager import VMManager

        path = tmp_path / "u.json"
        VMManager(storage_path=path).set_unattended("lab", enabled=True)
        assert VMManager(storage_path=path).is_unattended_enabled() is False

    def test_cli_set_mode_persists_and_model_stop_wins_in_process(self, tmp_path: Path):
        from tools.computer_use.vm_manager import VMManager

        path = tmp_path / "u.json"
        VMManager(storage_path=path).set_unattended("lab", enabled=True, persist=True)
        mgr = VMManager(storage_path=path)
        assert mgr.is_unattended_enabled() is True
        mgr.set_unattended(enabled=False)
        assert mgr.is_unattended_enabled() is False
        assert VMManager(storage_path=path).is_unattended_enabled() is True

    def test_wsl_is_not_reported_as_isolated(self, tmp_path: Path):
        from tools.computer_use.vm_manager import VMManager

        mgr = VMManager(storage_path=tmp_path / "u.json")
        mgr.set_unattended("Ubuntu", enabled=True)
        with patch.object(VMManager, "get_status", return_value={
                "ok": True, "status": {"state": "running", "vm_type": "wsl2"}}):
            st = mgr.get_unattended_status()
        assert "none" in st["isolation_type"]
        assert "NOT isolated" in st["message"]


def test_aux_vision_route_respects_max_elements():
    els = [UIElement(index=i, role="button", label=str(i), bounds=(0, 0, 1, 1)) for i in range(50)]
    cap = CaptureResult(mode="som", width=10, height=10, png_b64="iVBORw0KGgo=", elements=els)
    with patch("tools.vision_tools.vision_analyze_tool", return_value=None), \
         patch("model_tools._run_async", return_value=json.dumps({"analysis": "a window"})):
        out = json.loads(cu._route_capture_through_aux_vision(cap, "summary", max_elements=5))
    assert len(out["elements"]) == 5
    assert out["total_elements"] == 50


def test_cua_installer_is_pinned_to_a_commit():
    from tools.computer_use.cua_backend import CUA_INSTALLER_BASE, cua_driver_install_hint

    assert re.search(r"/trycua/cua/[0-9a-f]{40}/", CUA_INSTALLER_BASE)
    assert CUA_INSTALLER_BASE in cua_driver_install_hint()


class _FakeEngine:
    name = "fake"

    def __init__(self):
        self.calls = []

    def __getattr__(self, attr):
        return lambda *a: self.calls.append((attr, a))

    def get_cursor_position(self):
        return (400, 300)


class TestNativeBackend:
    def _backend(self):
        from tools.computer_use.native_backend import NativeBackend

        be = NativeBackend(max_width=0)
        be._engine = _FakeEngine()
        be._frame = (100, 50)
        return be

    def test_scroll_without_coordinate_scrolls_at_the_pointer(self):
        be = self._backend()
        be.scroll(direction="down", amount=2)
        assert be._engine.calls == [("scroll", (400, 300, "down", 2))]

    def test_coordinates_outside_the_last_screenshot_are_rejected(self):
        be = self._backend()
        for res in (be.click(x=100, y=10), be.mouse_move(x=-1, y=0),
                    be.drag(from_xy=(1, 1), to_xy=(5, 50)), be.scroll(direction="up", x=0, y=99)):
            assert res.ok is False and res.code == "out_of_bounds"
        assert be._engine.calls == []
        assert be.click(x=99, y=49).ok is True


@pytest.mark.skipif(sys.platform != "win32", reason="Windows SendInput engine")
class TestWindowsEngine:
    def _engine(self):
        from tools.computer_use.native_backend import _WindowsEngine

        eng = _WindowsEngine()
        eng.sent = []
        eng._send = lambda *inputs: eng.sent.extend(inputs)
        return eng

    def test_emoji_types_as_a_surrogate_pair(self):
        eng = self._engine()
        eng.type_text("a\U0001F600")
        scans = [i.u.ki.wScan for i in eng.sent if not i.u.ki.dwFlags & 0x0002]
        assert scans == [ord("a"), 0xD83D, 0xDE00]

    def test_newline_presses_enter(self):
        eng = self._engine()
        eng.type_text("a\r\nb")
        downs = [(i.u.ki.wVk, i.u.ki.wScan) for i in eng.sent if not i.u.ki.dwFlags & 0x0002]
        assert downs == [(0, ord("a")), (0x0D, 0), (0, ord("b"))]

    def test_unknown_key_raises_instead_of_silently_succeeding(self):
        eng = self._engine()
        with pytest.raises(ValueError):
            eng.key("ctrl+notakey")
        with pytest.raises(ValueError):
            eng.key("hyper+a")
        assert eng.sent == []

    def test_short_sendinput_delivery_raises(self):
        from tools.computer_use.native_backend import _WindowsEngine

        eng = _WindowsEngine()
        eng._user32 = MagicMock()
        eng._user32.SendInput.return_value = 0
        with pytest.raises(OSError):
            eng._send(eng._mk_key(0x41))


class TestUserTakeover:
    def _backend(self):
        from tools.computer_use.native_backend import NativeBackend

        be = NativeBackend(max_width=0)
        be._engine = _FakeEngine()
        be._frame = (1000, 1000)
        return be

    def test_input_pauses_after_the_user_moves_the_mouse_until_recapture(self):
        from PIL import Image

        be = self._backend()
        be._engine.get_cursor_position = lambda: (10, 10)
        assert be.click(x=10, y=10).ok is True
        be._engine.get_cursor_position = lambda: (500, 500)  # user grabbed the mouse
        for res in (be.click(x=20, y=20), be.type_text("x"), be.key("return")):
            assert res.ok is False and res.code == "user_active"
        with patch.object(type(be), "_grab", return_value=Image.new("RGB", (1000, 1000))):
            be.capture()
        assert be.click(x=30, y=30).ok is True

    def test_small_pointer_jitter_is_not_a_takeover(self):
        be = self._backend()
        be._engine.get_cursor_position = lambda: (12, 9)
        be._pointer_at(10, 10)
        assert be.click(x=50, y=50).ok is True


class TestZoom:
    def test_zoom_crops_full_resolution_without_changing_the_action_frame(self):
        from PIL import Image
        from tools.computer_use.native_backend import NativeBackend

        be = NativeBackend(max_width=0)
        be._engine = _FakeEngine()
        screen = Image.new("RGB", (2732, 1536))
        with patch.object(NativeBackend, "_grab", return_value=screen):
            be.capture()  # downscaled to 1366x768, scale 2.0
            out = be.zoom([100, 100, 300, 200])
        assert (out.width, out.height) == (400, 200)
        assert be._frame == (1366, 768) and be._scale_x == 2.0

    def test_zoom_rejects_bad_regions_and_missing_capture(self):
        from tools.computer_use.native_backend import NativeBackend

        be = NativeBackend(max_width=0)
        assert be.zoom([0, 0, 10, 10]).code == "no_capture"
        be._frame = (100, 100)
        assert be.zoom([50, 0, 10, 10]).code == "out_of_bounds"
        assert be.zoom([0, 0, 101, 10]).code == "out_of_bounds"

    def test_zoom_is_read_only_and_needs_no_approval(self):
        cb = MagicMock(return_value="deny")
        cu.set_approval_callback(cb)
        res = json.loads(cu.handle_computer_use({"action": "zoom", "region": [0, 0, 10, 10]}))
        cb.assert_not_called()
        assert res["ok"] is False and res["code"] == "unsupported"  # noop backend
