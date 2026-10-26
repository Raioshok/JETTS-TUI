"""Tests for the VM & VPS Management feature in the computer_use module."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.computer_use.schema import COMPUTER_USE_SCHEMA, VM_SCHEMA
from tools.computer_use.tool import (
    _DESTRUCTIVE_ACTIONS,
    _SAFE_ACTIONS,
    handle_computer_use,
    reset_backend_for_tests,
    set_approval_callback,
)
from tools.computer_use.vm_manager import (
    BaseVMProvider,
    HyperVProvider,
    QemuLibvirtProvider,
    RemoteVPSProvider,
    VirtualBoxProvider,
    VMExecutionResult,
    VMInfo,
    VMManager,
    VMwareProvider,
    WSLProvider,
    _hyperv_input_steps,
    _rgb565_to_png_bytes,
    _run_powershell,
    get_vm_manager,
)


def _register(name: str, host: str = "10.0.0.1") -> None:
    """Hosts are registered by the user (CLI), not through the model tool."""
    get_vm_manager().register_vm(name, vm_type="vps_ssh", os_type="linux", host=host, user="root")


@pytest.fixture(autouse=True)
def _reset_env(tmp_path: Path):
    """Tear down and use a temporary inventory path for isolation."""
    reset_backend_for_tests()
    set_approval_callback(None)
    temp_json = tmp_path / "vms.json"
    with patch("tools.computer_use.vm_manager.VMManager._default_storage_path", return_value=temp_json):
        # Reset global singleton
        import tools.computer_use.vm_manager as vmm
        vmm._global_vm_manager = None
        yield
        vmm._global_vm_manager = None
    set_approval_callback(None)
    reset_backend_for_tests()


class TestVMSchema:
    def test_vm_actions_live_in_vm_tool_not_computer_use(self):
        cu_actions = set(COMPUTER_USE_SCHEMA["parameters"]["properties"]["action"]["enum"])
        vm_actions = set(VM_SCHEMA["parameters"]["properties"]["action"]["enum"])
        assert vm_actions
        assert not {a for a in cu_actions if a.startswith(("vm_", "unattended_"))}
        assert not cu_actions & vm_actions

    def test_every_advertised_action_has_an_approval_class(self):
        for schema in (COMPUTER_USE_SCHEMA, VM_SCHEMA):
            for action in schema["parameters"]["properties"]["action"]["enum"]:
                assert action in _SAFE_ACTIONS | _DESTRUCTIVE_ACTIONS | {"set_value"}, action

    def test_no_schema_accepts_credentials(self):
        for schema in (COMPUTER_USE_SCHEMA, VM_SCHEMA):
            text = str(schema["parameters"]).lower()
            assert "password" not in text and "vm_config" not in text

    def test_model_cannot_register_hosts(self):
        res = json.loads(handle_computer_use({"action": "vm_register", "vm_name": "x", "target": "x"}))
        assert res.get("ok") is not True
        assert get_vm_manager().get_registered_vm("x") is None


class TestVMManagerRegistry:
    def test_register_and_unregister(self, tmp_path: Path):
        mgr = VMManager(storage_path=tmp_path / "vms.json")

        reg_res = mgr.register_vm(
            name="cloud-linux-1",
            vm_type="vps_ssh",
            os_type="linux",
            host="192.0.2.10",
            port=22,
            user="root",
            key_path="~/.ssh/id_rsa",
            notes="Production Linux VPS",
        )
        assert reg_res["ok"] is True

        # Check retrieval
        vm_cfg = mgr.get_registered_vm("cloud-linux-1")
        assert vm_cfg is not None
        assert vm_cfg["name"] == "cloud-linux-1"
        assert vm_cfg["host"] == "192.0.2.10"
        assert vm_cfg["os_type"] == "linux"

        # Check list
        vms = mgr.list_vms(include_discovered=False)
        assert len(vms) == 1
        assert vms[0]["name"] == "cloud-linux-1"

        # Check unregister
        unreg_res = mgr.unregister_vm("cloud-linux-1")
        assert unreg_res["ok"] is True
        assert mgr.get_registered_vm("cloud-linux-1") is None
        assert len(mgr.list_vms(include_discovered=False)) == 0

    def test_persistence_across_instances(self, tmp_path: Path):
        json_path = tmp_path / "vms.json"
        mgr1 = VMManager(storage_path=json_path)
        mgr1.register_vm("win-server-2022", vm_type="vps_winrm", os_type="windows", host="10.0.0.5")

        mgr2 = VMManager(storage_path=json_path)
        vm = mgr2.get_registered_vm("win-server-2022")
        assert vm is not None
        assert vm["os_type"] == "windows"
        assert vm["host"] == "10.0.0.5"


class TestVMProviders:
    def test_hyperv_provider_lifecycle(self):
        prov = HyperVProvider()
        with patch("tools.computer_use.vm_manager._run_powershell") as mock_ps:
            # Test start
            mock_ps.return_value = (0, "Started", "")
            res = prov.start("TestVM")
            assert res["ok"] is True
            assert "Start-VM" in mock_ps.call_args[0][0]

            # Test stop graceful
            mock_ps.return_value = (0, "Stopped", "")
            res = prov.stop("TestVM", force=False)
            assert res["ok"] is True
            assert mock_ps.call_args.kwargs["args"]["force"] is False

            # Test stop force
            res = prov.stop("TestVM", force=True)
            assert res["ok"] is True
            assert mock_ps.call_args.kwargs["args"]["force"] is True

            # Test restart
            res = prov.restart("TestVM", force=True)
            assert res["ok"] is True
            assert "Restart-VM" in mock_ps.call_args[0][0]

            # Test snapshot create
            mock_ps.return_value = (0, "Checkpoint", "")
            res = prov.snapshot("TestVM", "create", "snap1")
            assert res["ok"] is True
            assert "Checkpoint-VM" in mock_ps.call_args[0][0]

            # Test snapshot restore
            mock_ps.return_value = (0, "Restored", "")
            res = prov.snapshot("TestVM", "restore", "snap1")
            assert res["ok"] is True
            assert "Restore-VMSnapshot" in mock_ps.call_args[0][0]

    def test_hyperv_execute(self):
        prov = HyperVProvider()
        with patch("tools.computer_use.vm_manager._run_powershell") as mock_ps:
            mock_ps.return_value = (0, "hello world", "")
            res = prov.execute("TestVM", "echo 'hello world'", config={"user": "admin", "password": "pwd"})
            assert res.exit_code == 0
            assert res.stdout == "hello world"
            assert "Invoke-Command" in mock_ps.call_args[0][0]
            assert "System.Management.Automation.PSCredential" in mock_ps.call_args[0][0]

    def test_qemu_provider(self):
        prov = QemuLibvirtProvider()
        with patch("tools.computer_use.vm_manager._run_subprocess") as mock_sub:
            mock_sub.return_value = (0, "Domain TestQemu started", "")
            res = prov.start("TestQemu")
            assert res["ok"] is True
            assert mock_sub.call_args[0][0] == ["virsh", "start", "TestQemu"]

            # Test stop force
            mock_sub.return_value = (0, "Domain destroyed", "")
            res = prov.stop("TestQemu", force=True)
            assert res["ok"] is True
            assert mock_sub.call_args[0][0] == ["virsh", "destroy", "TestQemu"]

    def test_vmware_provider(self):
        prov = VMwareProvider()
        prov._vmrun_bin = "/usr/bin/vmrun"
        with patch("tools.computer_use.vm_manager._run_subprocess") as mock_sub:
            mock_sub.return_value = (0, "Success", "")
            res = prov.start("my-vm", config={"vmx_path": "/vms/my-vm.vmx"})
            assert res["ok"] is True
            assert "/vms/my-vm.vmx" in mock_sub.call_args[0][0]

    def test_virtualbox_provider(self):
        prov = VirtualBoxProvider()
        prov._vbox_bin = "/usr/bin/VBoxManage"
        with patch("tools.computer_use.vm_manager._run_subprocess") as mock_sub:
            mock_sub.return_value = (0, "Success", "")
            res = prov.start("my-vbox-vm")
            assert res["ok"] is True
            assert "startvm" in mock_sub.call_args[0][0]

    def test_remote_vps_provider(self):
        prov = RemoteVPSProvider()
        cfg = {"host": "192.168.1.100", "port": 2222, "user": "ubuntu", "os_type": "linux"}
        with patch("tools.computer_use.vm_manager._run_subprocess") as mock_sub:
            mock_sub.return_value = (0, "PONG", "")
            st = prov.get_status("my-vps", cfg)
            assert st is not None
            assert st.state == "running"
            assert "-p" in mock_sub.call_args[0][0]
            assert "2222" in mock_sub.call_args[0][0]


class TestComputerUseToolVMDispatch:
    def test_tool_vm_list_shows_registered(self):
        _register("test-agent-vps", "10.10.10.10")

        list_res = json.loads(handle_computer_use({"action": "vm_list"}))
        assert list_res["ok"] is True
        names = [v["name"] for v in list_res["vms"]]
        assert "test-agent-vps" in names

    def test_tool_vm_status(self):
        _register("status-vps", "10.10.10.20")
        with patch.object(RemoteVPSProvider, "get_status") as mock_status:
            mock_status.return_value = VMInfo(name="status-vps", vm_type="vps_ssh", os_type="linux", state="running")
            st_res = json.loads(handle_computer_use({"action": "vm_status", "vm_name": "status-vps"}))
            assert st_res["ok"] is True
            assert st_res["status"]["state"] == "running"

    def test_tool_vm_exec(self):
        _register("exec-vm", "10.10.10.30")
        with patch.object(RemoteVPSProvider, "execute") as mock_exec:
            mock_exec.return_value = VMExecutionResult(exit_code=0, stdout="uname: Linux", stderr="")
            res = json.loads(handle_computer_use({
                "action": "vm_exec",
                "vm_name": "exec-vm",
                "command": "uname -a",
            }))
            assert res["exit_code"] == 0
            assert "Linux" in res["stdout"]

    def test_tool_targeted_capture_routes_to_vm(self):
        _register("vis-vm", "10.10.10.40")
        fake_b64 = "iVBORw0KGgoAAAANSUhEUgAAAGQAAABkCAIAAAD/gAIDAAAA5UlEQVR4nO3SsREAIAwDscD+O8MK+V6qXf35vGHrrpeIVXhWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViDW7H2KXgHH3JQfGQAAAABJRU5ErkJggg=="
        with patch.object(RemoteVPSProvider, "capture_screen", return_value=(fake_b64, None)), \
             patch("tools.computer_use.tool._should_route_through_aux_vision", return_value=False):
            res = handle_computer_use({
                "action": "capture",
                "target": "vis-vm",
            })
            assert isinstance(res, dict)
            assert res.get("_multimodal") is True
            assert any("image_url" in item for item in res.get("content", []))

    def test_tool_targeted_input_routes_to_vm(self):
        _register("input-vm", "10.10.10.50")
        with patch.object(RemoteVPSProvider, "send_input", return_value={"ok": True, "message": "sent"}) as mock_input:
            res_str = handle_computer_use({
                "action": "type",
                "target": "input-vm",
                "text": "echo test",
            })
            res = json.loads(res_str)
            assert res["ok"] is True
            mock_input.assert_called_once()
            assert mock_input.call_args[1].get("text") == "echo test"

    def test_approval_callback_gates_destructive_vm_actions(self):
        cb_calls = []

        def mock_cb(action, args, summary):
            cb_calls.append(action)
            return "deny"

        set_approval_callback(mock_cb)

        # Destructive action: vm_start
        res_str = handle_computer_use({"action": "vm_start", "vm_name": "target-vm"})
        res = json.loads(res_str)
        assert res.get("error") == "denied by user"
        assert "vm_start" in cb_calls

        # Read-only action: vm_list bypasses approval
        res_list = json.loads(handle_computer_use({"action": "vm_list"}))
        assert res_list.get("ok") is True


class TestUnattendedComputerUse:
    def test_unattended_set_and_status(self, tmp_path: Path):
        mgr = VMManager(storage_path=tmp_path / "vms.json")
        mgr.register_vm("sandbox-win", vm_type="hyperv", os_type="windows")

        res = mgr.set_unattended("sandbox-win", enabled=True)
        assert res["ok"] is True
        assert res["unattended_enabled"] is True

        st = mgr.get_unattended_status()
        assert st["ok"] is True
        assert st["unattended_enabled"] is True
        assert st["active_target"] == "sandbox-win"
        assert st["host_input_protected"] is True

        # Disable
        res2 = mgr.set_unattended(enabled=False)
        assert res2["unattended_enabled"] is False
        assert mgr.is_unattended_enabled() is False

    def test_unattended_auto_routing_without_target_arg(self):
        _register("auto-vm", "10.0.0.1")
        handle_computer_use({
            "action": "unattended_set",
            "target": "auto-vm",
        })

        with patch.object(RemoteVPSProvider, "send_input", return_value={"ok": True, "message": "unattended input"}) as mock_inp:
            res_str = handle_computer_use({
                "action": "type",
                "text": "unattended typing",
                "unattended": True,
            })
            res = json.loads(res_str)
            assert res["ok"] is True
            mock_inp.assert_called_once()
            assert mock_inp.call_args[1].get("text") == "unattended typing"

    def test_coordinate_scaling(self, tmp_path: Path):
        mgr = VMManager(storage_path=tmp_path / "vms.json")
        mgr.register_vm("test-vm", vm_type="vps_ssh", os_type="linux")
        # 100x100 fake image
        fake_b64 = "iVBORw0KGgoAAAANSUhEUgAAAGQAAABkCAIAAAD/gAIDAAAA5UlEQVR4nO3SsREAIAwDscD+O8MK+V6qXf35vGHrrpeIVXhWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViBWIFYgViDW7H2KXgHH3JQfGQAAAABJRU5ErkJggg=="

        with patch.object(RemoteVPSProvider, "capture_screen", return_value=(fake_b64, None)):
            b64_out, err, w, h = mgr.capture_screen("test-vm", max_width=50)
            assert err is None
            assert w == 50
            assert h == 50
            # Scale should be 100 / 50 = 2.0
            assert mgr._scales["test-vm"] == (2.0, 2.0)

        with patch.object(RemoteVPSProvider, "send_input", return_value={"ok": True}) as mock_in:
            mgr.send_input("test-vm", "click", x=25, y=30)
            # The click coordinate [25, 30] should be rescaled by 2.0 to [50, 60]!
            assert mock_in.call_args[1]["x"] == 50
            assert mock_in.call_args[1]["y"] == 60


class TestClaudeReferenceCompatibilityAndSpeed:
    def test_claude_action_aliases(self):
        # 1. screenshot -> capture
        with patch("tools.computer_use.tool._get_backend") as mock_gb:
            mock_backend = MagicMock()
            from tools.computer_use.backend import CaptureResult
            mock_backend.capture.return_value = CaptureResult(
                mode="vision", width=1280, height=720, png_b64="fake", elements=[]
            )
            mock_gb.return_value = mock_backend
            with patch("tools.computer_use.tool._should_route_through_aux_vision", return_value=False):
                res = handle_computer_use({"action": "screenshot"})
                assert isinstance(res, dict)
                assert res.get("_multimodal") is True

        # 2. left_click -> click
        with patch("tools.computer_use.tool._get_backend") as mock_gb:
            mock_backend = MagicMock()
            from tools.computer_use.backend import ActionResult
            mock_backend.click.return_value = ActionResult(ok=True, action="click")
            mock_gb.return_value = mock_backend
            res_str = handle_computer_use({"action": "left_click", "coordinate": [100, 200]})
            assert json.loads(res_str)["ok"] is True
            assert mock_backend.click.call_args[1]["button"] == "left"

        # 3. left_click_drag with start_coordinate
        with patch("tools.computer_use.tool._get_backend") as mock_gb:
            mock_backend = MagicMock()
            mock_backend.drag.return_value = ActionResult(ok=True, action="drag")
            mock_gb.return_value = mock_backend
            res_str = handle_computer_use({
                "action": "left_click_drag",
                "start_coordinate": [10, 20],
                "coordinate": [100, 200],
            })
            assert json.loads(res_str)["ok"] is True
            assert mock_backend.drag.call_args[1]["from_xy"] == (10, 20)
            assert mock_backend.drag.call_args[1]["to_xy"] == (100, 200)

        # 4. cursor_position
        with patch("tools.computer_use.tool._get_backend") as mock_gb:
            mock_backend = MagicMock()
            mock_backend.cursor_position.return_value = ActionResult(
                ok=True, action="cursor_position", message="X=123,Y=456", meta={"coordinate": [123, 456]}
            )
            mock_gb.return_value = mock_backend
            res_str = handle_computer_use({"action": "cursor_position"})
            res = json.loads(res_str)
            assert res["ok"] is True
            assert res["message"] == "X=123,Y=456"

        # 5. mouse_move
        with patch("tools.computer_use.tool._get_backend") as mock_gb:
            mock_backend = MagicMock()
            mock_backend.mouse_move.return_value = ActionResult(ok=True, action="mouse_move")
            mock_gb.return_value = mock_backend
            res_str = handle_computer_use({"action": "mouse_move", "coordinate": [50, 75]})
            assert json.loads(res_str)["ok"] is True
            assert mock_backend.mouse_move.call_args[1]["x"] == 50
            assert mock_backend.mouse_move.call_args[1]["y"] == 75

        # 6. triple_click
        with patch("tools.computer_use.tool._get_backend") as mock_gb:
            mock_backend = MagicMock()
            mock_backend.click.return_value = ActionResult(ok=True, action="triple_click")
            mock_gb.return_value = mock_backend
            res_str = handle_computer_use({"action": "triple_click", "coordinate": [50, 75]})
            assert json.loads(res_str)["ok"] is True
            assert mock_backend.click.call_args[1]["click_count"] == 3

    def test_claude_parameter_aliases(self):
        with patch("tools.computer_use.tool._get_backend") as mock_gb:
            mock_backend = MagicMock()
            from tools.computer_use.backend import ActionResult
            mock_backend.scroll.return_value = ActionResult(ok=True, action="scroll")
            mock_backend.key.return_value = ActionResult(ok=True, action="key")
            mock_backend.wait.return_value = ActionResult(ok=True, action="wait")
            mock_gb.return_value = mock_backend

            # scroll_direction / scroll_amount
            handle_computer_use({"action": "scroll", "scroll_direction": "up", "scroll_amount": 5})
            assert mock_backend.scroll.call_args[1]["direction"] == "up"
            assert mock_backend.scroll.call_args[1]["amount"] == 5

            # duration -> seconds
            handle_computer_use({"action": "wait", "duration": 2.5})
            mock_backend.wait.assert_called_with(2.5)

            # key -> keys
            handle_computer_use({"action": "key", "key": "Return"})
            assert mock_backend.key.call_args[0][0] == "Return"

    def test_native_backend_claude_aspect_ratio_scaling(self):
        from tools.computer_use.native_backend import NativeBackend
        from PIL import Image

        be = NativeBackend(max_width=0)
        # 16:9 1920x1080 display should scale to FWXGA (1366x768)
        with patch.object(NativeBackend, "_grab", return_value=Image.new("RGB", (1920, 1080))):
            cap = be.capture()
            assert cap.width == 1366
            assert cap.height == 768
            # Scale x should be 1920 / 1366 ~= 1.4055
            assert round(be._scale_x, 2) == 1.41
            assert round(be._scale_y, 2) == 1.41

        # 16:10 1920x1200 display should scale to WXGA (1280x800)
        with patch.object(NativeBackend, "_grab", return_value=Image.new("RGB", (1920, 1200))):
            cap = be.capture()
            assert cap.width == 1280
            assert cap.height == 800

        # 4:3 1600x1200 display should scale to XGA (1024x768)
        with patch.object(NativeBackend, "_grab", return_value=Image.new("RGB", (1600, 1200))):
            cap = be.capture()
            assert cap.width == 1024
            assert cap.height == 768

    def test_wsl_provider_discovery_and_exec(self):
        from tools.computer_use.vm_manager import WSLProvider
        prov = WSLProvider()
        fake_wsl_output = "NAME              STATE           VERSION\n* Ubuntu          Running         2\n  Debian          Stopped         2\n"

        with patch("subprocess.run") as mock_sub:
            mock_sub.return_value = MagicMock(returncode=0, stdout=fake_wsl_output)
            vms = prov.list_vms()
            assert len(vms) == 2
            assert vms[0].name == "Ubuntu"
            assert vms[0].state == "running"
            assert vms[0].vm_type == "wsl2"
            assert vms[1].name == "Debian"
            assert vms[1].state == "stopped"

        with patch("tools.computer_use.vm_manager._run_subprocess") as mock_run:
            mock_run.return_value = (0, "Linux 6.1", "")
            res = prov.execute("Ubuntu", "uname -r")
            assert res.exit_code == 0
            assert "Linux 6.1" in res.stdout
            assert mock_run.call_args[0][0] == ["wsl.exe", "-d", "Ubuntu", "--", "sh", "-c", "uname -r"]

    def test_hyperv_file_download_guest_to_host(self):
        prov = HyperVProvider()
        with patch("tools.computer_use.vm_manager._run_powershell") as mock_ps:
            mock_ps.return_value = (0, "Downloaded", "")
            res = prov.transfer_file(
                "Aegis-Lab-Win11",
                source="C:\\guest\\log.txt",
                dest="C:\\host\\log.txt",
                direction="download",
            )
            assert res["ok"] is True
            assert "ReadAllBytes" in mock_ps.call_args[0][0]
            assert "WriteAllBytes" in mock_ps.call_args[0][0]


class TestCredentialsAndInjection:
    def test_password_is_never_written_to_inventory(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("LAB_PW", "s3cret!")
        mgr = VMManager(storage_path=tmp_path / "vms.json")
        mgr.register_vm("lab", vm_type="hyperv", os_type="windows", user="admin", password_env="LAB_PW")
        assert "s3cret!" not in (tmp_path / "vms.json").read_text(encoding="utf-8")
        _, cfg = mgr._resolve_target("lab")
        assert cfg["password"] == "s3cret!"
        assert all("s3cret!" not in json.dumps(v) for v in mgr.list_vms(include_discovered=False))

    def test_hyperv_values_never_reach_script_text(self):
        evil = "x'; Remove-Item C:\\ -Recurse #\"$(calc)"
        prov = HyperVProvider()
        with patch("tools.computer_use.vm_manager._run_powershell", return_value=(0, "", "")) as mock_ps:
            prov.start(evil)
            prov.snapshot(evil, "restore", evil)
            prov.execute(evil, evil, config={"user": evil, "password": evil})
            prov.transfer_file(evil, evil, evil, direction="download")
            prov.send_input(evil, "type", text=evil)
        assert mock_ps.call_count == 5
        for call in mock_ps.call_args_list:
            assert evil not in call[0][0]
            assert call.kwargs["args"]["name"] == evil

    @pytest.mark.skipif(sys.platform != "win32", reason="needs powershell.exe")
    def test_run_powershell_passes_args_literally(self):
        evil = "x'; $(Write-Output pwned) \"q`n"
        code, out, err = _run_powershell("Write-Output $a.v", timeout=60, args={"v": evil})
        assert code == 0, err
        assert out == evil
        code, out, err = _run_powershell("throw 'boom'", timeout=60)
        assert code == 1 and err == "boom"

    def test_wsl_transfer_uses_argv_not_host_shell(self):
        with patch("tools.computer_use.vm_manager._run_subprocess", return_value=(0, "", "")) as mock_run:
            WSLProvider().transfer_file("Ubuntu", "C:\\a b.txt", "/tmp/$(x)", direction="upload")
        argv = mock_run.call_args[0][0]
        assert argv[:4] == ["wsl.exe", "-d", "Ubuntu", "--"]
        assert argv[-2:] == ["C:\\a b.txt", "/tmp/$(x)"]
        assert not mock_run.call_args.kwargs.get("shell")


class TestHyperVInputSteps:
    def test_key_combo_presses_modifiers_around_final_key(self):
        steps = _hyperv_input_steps("key", keys="ctrl+alt+t")
        assert [(s["m"], s["p"]["keyCode"]) for s in steps] == [
            ("PressKey", 0x11), ("PressKey", 0x12), ("TypeKey", ord("T")),
            ("ReleaseKey", 0x12), ("ReleaseKey", 0x11),
        ]

    def test_unknown_key_is_an_error_not_a_guess(self):
        assert isinstance(_hyperv_input_steps("key", keys="ctrl+nonsense"), str)

    def test_long_text_is_chunked_within_typetext_limit(self):
        text = "a" * 700
        steps = _hyperv_input_steps("type", text=text)
        assert "".join(s["p"]["asciiText"] for s in steps) == text
        assert all(len(s["p"]["asciiText"]) <= 256 for s in steps)

    def test_double_click_moves_then_clicks_twice(self):
        steps = _hyperv_input_steps("double_click", x=10, y=20)
        assert steps[0]["p"] == {"horizontalPosition": 10, "verticalPosition": 20}
        presses = [s["p"]["isDown"] for s in steps if s.get("m") == "SetButtonState"]
        assert presses == [True, False, True, False]

    def test_drag_ends_at_target_with_button_released(self):
        steps = _hyperv_input_steps("drag", from_xy=(0, 0), to_xy=(100, 50))
        moves = [s["p"] for s in steps if s.get("m") == "SetAbsolutePosition"]
        assert moves[0] == {"horizontalPosition": 0, "verticalPosition": 0}
        assert moves[-1] == {"horizontalPosition": 100, "verticalPosition": 50}
        assert steps[-1]["p"]["isDown"] is False

    def test_rgb565_decodes_primary_colors(self):
        import io
        import struct
        from PIL import Image
        png = _rgb565_to_png_bytes(struct.pack("<3H", 0xF800, 0x07E0, 0x001F), 3, 1)
        img = Image.open(io.BytesIO(png)).convert("RGB")
        assert [img.getpixel((i, 0)) for i in range(3)] == [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
