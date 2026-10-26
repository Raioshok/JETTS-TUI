"""VM and VPS Management Feature for the Computer Use module.

Provides unified discovery, lifecycle management, snapshot operations, guest
command execution, file transfers, and unattended remote GUI desktop automation
(screen capture, input injection, and coordinate scaling) across Linux and Windows
virtual machines and VPSes.

Supported virtualization and remote targets:
  - Windows Hyper-V VMs (local Windows host, PowerShell Direct, WMI, cmdlets)
  - QEMU / KVM / libvirt VMs (virsh)
  - VMware Workstation / Fusion / Player (vmrun)
  - VirtualBox VMs (VBoxManage)
  - Remote Linux VPSes / cloud instances (SSH / SCP)
  - Remote Windows VPSes / cloud instances (WinRM / OpenSSH / PowerShell Remoting)

Unattended Computer Use Architecture:
  Runs desktop automation inside an isolated virtual machine or remote VPS so that
  the user can actively use their host PC (type, click, game, code) simultaneously
  with ZERO cursor hijacking, zero focus stealing, and zero input collision.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class VMInfo:
    """Standardized representation of a virtual machine or remote VPS."""

    name: str
    vm_type: str  # "hyperv", "qemu", "vmware", "virtualbox", "vps_ssh", "vps_winrm"
    os_type: str  # "linux", "windows", "other"
    state: str  # "running", "stopped", "paused", "saved", "unknown"
    host: Optional[str] = None
    port: Optional[int] = None
    user: Optional[str] = None
    ip_addresses: List[str] = field(default_factory=list)
    uptime_seconds: Optional[float] = None
    cpu_count: Optional[int] = None
    memory_mb: Optional[int] = None
    notes: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VMSnapshotInfo:
    """Snapshot or checkpoint information."""

    name: str
    snapshot_id: Optional[str] = None
    created_at: Optional[str] = None
    description: Optional[str] = None
    is_current: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VMExecutionResult:
    """Result of running a command inside a VM or VPS."""

    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Subprocess & Shell Helpers
# ---------------------------------------------------------------------------


def _run_subprocess(
    cmd: Union[List[str], str],
    timeout: float = 30.0,
    input_data: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    shell: bool = False,
) -> Tuple[int, str, str]:
    """Execute a subprocess command with timeout and UTF-8 handling."""
    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    try:
        proc = subprocess.run(
            cmd,
            input=input_data,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=shell,
            env=run_env,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode("utf-8", errors="replace") if exc.stdout else ""
        err = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        return -1, out, f"Execution timed out after {timeout}s: {err}"
    except Exception as exc:
        return -1, "", str(exc)


def _run_powershell(
    script: str,
    timeout: float = 45.0,
    args: Optional[Dict[str, Any]] = None,
) -> Tuple[int, str, str]:
    """Execute a PowerShell script using powershell.exe or pwsh.

    Values in ``args`` reach the script as ``$a.<key>`` through an env var,
    never through string interpolation, so names, paths and passwords cannot
    inject code. Errors come back as plain text on stderr (exit code 1).
    """
    pwsh = shutil.which("pwsh") or shutil.which("powershell.exe") or "powershell.exe"
    env = None
    if args is not None:
        script = "$a = $env:JETTSTUI_PS_ARGS | ConvertFrom-Json\n" + script
        env = {"JETTSTUI_PS_ARGS": json.dumps(args)}
    # The try/catch keeps -EncodedCommand from emitting CLIXML on stderr.
    wrapped = (
        "$ProgressPreference = 'SilentlyContinue'\n$ErrorActionPreference = 'Stop'\n"
        f"try {{\n{script}\n}} catch {{ [Console]::Error.WriteLine($_.Exception.Message); exit 1 }}"
    )
    encoded = base64.b64encode(wrapped.encode("utf-16le")).decode("ascii")
    cmd = [pwsh, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded]
    return _run_subprocess(cmd, timeout=timeout, env=env)


def _convert_ppm_to_png_bytes(ppm_data: bytes) -> Optional[bytes]:
    """Convert binary PPM (P6) bytes to PNG bytes using Pillow."""
    try:
        import io
        from PIL import Image

        image = Image.open(io.BytesIO(ppm_data))
        out_buf = io.BytesIO()
        image.save(out_buf, format="PNG")
        return out_buf.getvalue()
    except Exception as exc:
        logger.debug("Failed to convert PPM to PNG: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Base Provider Interface
# ---------------------------------------------------------------------------


class BaseVMProvider:
    """Abstract provider for a specific virtualization hypervisor or remote protocol."""

    def is_available(self) -> bool:
        """Return True if this provider's tooling is installed/accessible on this host."""
        return False

    def list_vms(self) -> List[VMInfo]:
        """Discover virtual machines managed by this hypervisor."""
        return []

    def get_status(self, name: str, config: Optional[Dict[str, Any]] = None) -> Optional[VMInfo]:
        """Fetch real-time state and metrics for the specified VM."""
        return None

    def start(self, name: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Power on / start VM."""
        return {"ok": False, "error": "Not implemented"}

    def stop(self, name: str, force: bool = False, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Stop / shut down VM."""
        return {"ok": False, "error": "Not implemented"}

    def restart(self, name: str, force: bool = False, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Restart / reboot VM."""
        return {"ok": False, "error": "Not implemented"}

    def pause(self, name: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Pause / suspend VM."""
        return {"ok": False, "error": "Not implemented"}

    def resume(self, name: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Resume paused / suspended VM."""
        return {"ok": False, "error": "Not implemented"}

    def snapshot(
        self,
        name: str,
        operation: str,
        snapshot_name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Manage snapshots: operation in ('create', 'restore', 'delete', 'list')."""
        return {"ok": False, "error": "Not implemented"}

    def execute(
        self,
        name: str,
        command: str,
        timeout: float = 60.0,
        config: Optional[Dict[str, Any]] = None,
    ) -> VMExecutionResult:
        """Execute command inside the guest OS."""
        return VMExecutionResult(exit_code=-1, stdout="", stderr="Not implemented")

    def transfer_file(
        self,
        name: str,
        source: str,
        dest: str,
        direction: str = "upload",  # "upload" (host->guest) or "download" (guest->host)
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Transfer files to/from guest."""
        return {"ok": False, "error": "Not implemented"}

    def capture_screen(self, name: str, config: Optional[Dict[str, Any]] = None) -> Tuple[Optional[str], Optional[str]]:
        """Capture screenshot from VM console/guest. Returns (png_b64, error)."""
        return None, "Not implemented"

    def send_input(
        self,
        name: str,
        action: str,
        config: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Send keyboard or pointer input into the VM."""
        return {"ok": False, "error": "Not implemented"}


# ---------------------------------------------------------------------------
# Hyper-V Provider (Windows Host)
# ---------------------------------------------------------------------------


class HyperVProvider(BaseVMProvider):
    """Hyper-V management for Windows and Linux guests on Windows host.

    Lifecycle uses the Hyper-V cmdlets. Screen capture and input go through the
    host-side WMI devices (thumbnail image, Msvm_Keyboard, Msvm_SyntheticMouse),
    the same path vmconnect uses, so they work for any guest OS without an
    interactive session inside the guest.
    """

    def is_available(self) -> bool:
        if sys.platform != "win32":
            return False
        # Quick check if Hyper-V cmdlets are present
        code, out, _ = _run_powershell("Get-Command Get-VM -ErrorAction SilentlyContinue", timeout=5.0)
        return code == 0 and bool(out)

    def list_vms(self) -> List[VMInfo]:
        script = """
        $list = @()
        foreach ($v in Get-VM) {
            $ips = @()
            $adap = Get-VMNetworkAdapter -VMName $v.Name -ErrorAction SilentlyContinue
            if ($adap) { $ips = $adap.IPAddresses }
            $list += [PSCustomObject]@{
                Name = $v.Name
                State = $v.State.ToString()
                MemoryMB = [math]::Round($v.MemoryAssigned / 1MB)
                UptimeSeconds = if ($v.Uptime) { $v.Uptime.TotalSeconds } else { 0 }
                IPAddresses = $ips
                Id = $v.Id.ToString()
            }
        }
        ConvertTo-Json -Depth 3 -Compress -InputObject @($list)
        """
        code, out, err = _run_powershell(script, timeout=15.0)
        if code != 0 or not out:
            logger.debug("Hyper-V list_vms returned non-zero or empty: %s", err)
            return []

        try:
            data = json.loads(out)
            if isinstance(data, dict):
                data = [data]
            results: List[VMInfo] = []
            for item in data:
                raw_state = str(item.get("State", "")).lower()
                state = "running" if raw_state in ("running", "2") else "stopped"
                if "paused" in raw_state or "suspended" in raw_state:
                    state = "paused"
                name = str(item.get("Name", ""))
                # Infer OS from VM name or default to Windows/Linux based on pattern
                os_type = "linux" if any(k in name.lower() for k in ("ubuntu", "debian", "arch", "centos", "rhel", "linux")) else "windows"
                ips = item.get("IPAddresses") or []
                if isinstance(ips, str):
                    ips = [ips]
                results.append(
                    VMInfo(
                        name=name,
                        vm_type="hyperv",
                        os_type=os_type,
                        state=state,
                        ip_addresses=[str(ip) for ip in ips if ip and ":" not in str(ip)],
                        uptime_seconds=float(item.get("UptimeSeconds") or 0.0),
                        memory_mb=int(item.get("MemoryMB") or 0),
                        cpu_count=None,
                        extra={"id": item.get("Id", "")},
                    )
                )
            return results
        except Exception as exc:
            logger.debug("Failed parsing Hyper-V list JSON: %s (raw=%r)", exc, out)
            return []

    def get_status(self, name: str, config: Optional[Dict[str, Any]] = None) -> Optional[VMInfo]:
        vms = self.list_vms()
        for vm in vms:
            if vm.name.lower() == name.lower():
                return vm
        return None

    def _cmdlet(self, script: str, args: Dict[str, Any], ok_msg: str, timeout: float = 30.0) -> Dict[str, Any]:
        code, out, err = _run_powershell(script, timeout=timeout, args=args)
        return {"ok": code == 0, "message": out or (ok_msg if code == 0 else err)}

    def start(self, name: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._cmdlet("Start-VM -Name $a.name", {"name": name}, "Started", timeout=20.0)

    def stop(self, name: str, force: bool = False, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._cmdlet("Stop-VM -Name $a.name -TurnOff:$a.force", {"name": name, "force": force}, "Stopped")

    def restart(self, name: str, force: bool = False, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._cmdlet("Restart-VM -Name $a.name -Force:$a.force", {"name": name, "force": force}, "Restarted")

    def pause(self, name: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._cmdlet("Suspend-VM -Name $a.name", {"name": name}, "Suspended", timeout=20.0)

    def resume(self, name: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._cmdlet("Resume-VM -Name $a.name", {"name": name}, "Resumed", timeout=20.0)

    def snapshot(
        self,
        name: str,
        operation: str,
        snapshot_name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        op = operation.lower().strip()
        args = {"name": name, "snap": snapshot_name}
        if op == "create":
            args["snap"] = snapshot_name or f"snapshot_{int(time.time())}"
            res = self._cmdlet("Checkpoint-VM -Name $a.name -SnapshotName $a.snap", args, "Snapshot created")
            return {**res, "snapshot_name": args["snap"]}
        if op in ("restore", "delete"):
            if not snapshot_name:
                return {"ok": False, "error": f"snapshot_name is required for {op}"}
            verb = "Restore-VMSnapshot" if op == "restore" else "Remove-VMSnapshot"
            return self._cmdlet(f"{verb} -VMName $a.name -Name $a.snap -Confirm:$false", args,
                                "Snapshot restored" if op == "restore" else "Snapshot deleted", timeout=45.0)
        if op == "list":
            script = """
            $snaps = Get-VMSnapshot -VMName $a.name | Select-Object Name, CreationTime, Id
            ConvertTo-Json -Depth 2 -Compress -InputObject @($snaps)
            """
            code, out, err = _run_powershell(script, timeout=15.0, args=args)
            if code != 0:
                return {"ok": False, "error": err}
            snaps: List[Dict[str, Any]] = []
            if out:
                try:
                    parsed = json.loads(out)
                    if isinstance(parsed, dict):
                        parsed = [parsed]
                    for s in parsed:
                        snaps.append({
                            "name": s.get("Name", ""),
                            "created_at": str(s.get("CreationTime", "")),
                            "id": s.get("Id", ""),
                        })
                except Exception:
                    pass
            return {"ok": True, "snapshots": snaps, "count": len(snaps)}
        return {"ok": False, "error": f"Unknown snapshot operation: {operation}"}

    # PowerShell Direct credential, built from $a.user / $a.password (never interpolated).
    _CRED = """
    $cred = $null
    if ($a.user -and $a.password) {
        $cred = New-Object System.Management.Automation.PSCredential($a.user, (ConvertTo-SecureString $a.password -AsPlainText -Force))
    }
    $ic = @{ VMName = $a.name }
    if ($cred) { $ic.Credential = $cred }
    """

    def _direct_args(self, name: str, config: Optional[Dict[str, Any]], **extra: Any) -> Dict[str, Any]:
        cfg = config or {}
        return {"name": name, "user": cfg.get("user"), "password": cfg.get("password"), **extra}

    def execute(
        self,
        name: str,
        command: str,
        timeout: float = 60.0,
        config: Optional[Dict[str, Any]] = None,
    ) -> VMExecutionResult:
        script = self._CRED + """
        Invoke-Command @ic -ArgumentList $a.cmd -ScriptBlock { param($c) Invoke-Expression $c }
        """
        start_t = time.time()
        code, out, err = _run_powershell(script, timeout=timeout, args=self._direct_args(name, config, cmd=command))
        duration = time.time() - start_t
        return VMExecutionResult(exit_code=code, stdout=out, stderr=err, duration_seconds=round(duration, 3))

    def transfer_file(
        self,
        name: str,
        source: str,
        dest: str,
        direction: str = "upload",
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        args = self._direct_args(name, config, src=source, dest=dest)
        if direction == "upload":
            script = "Copy-VMFile -Name $a.name -SourcePath $a.src -DestinationPath $a.dest -CreateFullPath -FileSource Host"
            return self._cmdlet(script, args, "Uploaded", timeout=60.0)
        script = self._CRED + """
        $bytes = Invoke-Command @ic -ArgumentList $a.src -ScriptBlock { param($p) [System.IO.File]::ReadAllBytes($p) }
        [System.IO.File]::WriteAllBytes($a.dest, [byte[]]$bytes)
        """
        return self._cmdlet(script, args, "Downloaded", timeout=120.0)

    # Resolves $vm plus a Get-Dev helper for the VM's WMI devices.
    _WMI_VM = """
    $ns = 'root\\virtualization\\v2'
    $vm = Get-CimInstance -Namespace $ns -ClassName Msvm_ComputerSystem | Where-Object { $_.ElementName -eq $a.name } | Select-Object -First 1
    if (-not $vm) { throw "Hyper-V VM not found: $($a.name)" }
    """

    def capture_screen(self, name: str, config: Optional[Dict[str, Any]] = None) -> Tuple[Optional[str], Optional[str]]:
        script = self._WMI_VM + """
        $vh = Get-CimAssociatedInstance -InputObject $vm -ResultClassName Msvm_VideoHead | Select-Object -First 1
        if (-not $vh -or -not $vh.CurrentHorizontalResolution) { throw "VM '$($a.name)' has no active display (is it running?)" }
        $w = [int]$vh.CurrentHorizontalResolution; $h = [int]$vh.CurrentVerticalResolution
        $vssd = Get-CimAssociatedInstance -InputObject $vm -ResultClassName Msvm_VirtualSystemSettingData |
            Where-Object { $_.VirtualSystemType -eq 'Microsoft:Hyper-V:System:Realized' } | Select-Object -First 1
        $svc = Get-CimInstance -Namespace $ns -ClassName Msvm_VirtualSystemManagementService
        $r = Invoke-CimMethod -InputObject $svc -MethodName GetVirtualSystemThumbnailImage -Arguments @{
            TargetSystem = $vssd; WidthPixels = [uint16]$w; HeightPixels = [uint16]$h }
        if ($r.ReturnValue -ne 0) { throw "GetVirtualSystemThumbnailImage returned $($r.ReturnValue)" }
        "$w $h " + [Convert]::ToBase64String([byte[]]$r.ImageData)
        """
        code, out, err = _run_powershell(script, timeout=30.0, args={"name": name})
        if code != 0 or not out:
            return None, f"Hyper-V screen capture failed: {err or 'no output'}"
        try:
            w, h, b64 = out.split(" ", 2)
            png = _rgb565_to_png_bytes(base64.b64decode(b64), int(w), int(h))
        except Exception as exc:
            return None, f"Hyper-V screen capture returned unreadable data: {exc}"
        return base64.b64encode(png).decode("ascii"), None

    def send_input(
        self,
        name: str,
        action: str,
        config: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        steps = _hyperv_input_steps(action, **kwargs)
        if isinstance(steps, str):
            return {"ok": False, "error": steps}
        script = self._WMI_VM + """
        $devs = @{}
        foreach ($s in $a.steps) {
            if ($s.sleep) { Start-Sleep -Milliseconds $s.sleep; continue }
            if (-not $devs[$s.dev]) {
                $devs[$s.dev] = Get-CimAssociatedInstance -InputObject $vm -ResultClassName $s.dev | Select-Object -First 1
                if (-not $devs[$s.dev]) { throw "$($s.dev) is unavailable for '$($a.name)' (VM off, or guest lacks Hyper-V integration services)" }
            }
            $p = @{}
            foreach ($prop in $s.p.PSObject.Properties) { $p[$prop.Name] = $prop.Value }
            $r = Invoke-CimMethod -InputObject $devs[$s.dev] -MethodName $s.m -Arguments $p
            if ($r.ReturnValue -ne 0) { throw "$($s.dev).$($s.m) returned $($r.ReturnValue)" }
        }
        """
        code, out, err = _run_powershell(script, timeout=20.0, args={"name": name, "steps": steps})
        return {"ok": code == 0, "message": out or (action if code == 0 else err)}


# Windows virtual-key codes for Msvm_Keyboard (letters/digits map to their ASCII code).
_VK_CODES: Dict[str, int] = {
    "backspace": 0x08, "tab": 0x09, "return": 0x0D, "enter": 0x0D, "shift": 0x10,
    "ctrl": 0x11, "control": 0x11, "alt": 0x12, "option": 0x12, "pause": 0x13,
    "capslock": 0x14, "escape": 0x1B, "esc": 0x1B, "space": 0x20, "pageup": 0x21,
    "pagedown": 0x22, "end": 0x23, "home": 0x24, "left": 0x25, "up": 0x26,
    "right": 0x27, "down": 0x28, "insert": 0x2D, "delete": 0x2E, "del": 0x2E,
    "win": 0x5B, "cmd": 0x5B, "super": 0x5B, "meta": 0x5B, "windows": 0x5B,
    **{f"f{i}": 0x6F + i for i in range(1, 13)},
}
_MOUSE_BUTTONS = {"left": 1, "right": 2, "middle": 3}
_TYPE_TEXT_CHUNK = 256  # Msvm_Keyboard.TypeText accepts at most 256-512 chars per call


def _vk(key: str) -> Optional[int]:
    key = key.strip().lower()
    if len(key) == 1 and key.isalnum():
        return ord(key.upper())
    return _VK_CODES.get(key)


def _hyperv_input_steps(action: str, **kw: Any) -> Union[List[Dict[str, Any]], str]:
    """Translate a computer_use input action into Msvm_Keyboard/Msvm_SyntheticMouse calls.

    Returns the step list, or an error string for unsupported input.
    """
    kb, mouse = "Msvm_Keyboard", "Msvm_SyntheticMouse"

    def move(x: Any, y: Any) -> Dict[str, Any]:
        return {"dev": mouse, "m": "SetAbsolutePosition",
                "p": {"horizontalPosition": int(x), "verticalPosition": int(y)}}

    def button(idx: int, down: bool) -> Dict[str, Any]:
        return {"dev": mouse, "m": "SetButtonState", "p": {"buttonIndex": idx, "isDown": down}}

    if action == "type":
        text = kw.get("text") or ""
        if not text:
            return "type requires text"
        return [{"dev": kb, "m": "TypeText", "p": {"asciiText": text[i:i + _TYPE_TEXT_CHUNK]}}
                for i in range(0, len(text), _TYPE_TEXT_CHUNK)]

    if action == "key":
        parts = [p for p in re.split(r"\s*\+\s*", kw.get("keys") or "") if p]
        codes = [_vk(p) for p in parts]
        if not parts or None in codes:
            return f"unsupported key combo {kw.get('keys')!r}"
        *mods, last = codes
        return ([{"dev": kb, "m": "PressKey", "p": {"keyCode": c}} for c in mods]
                + [{"dev": kb, "m": "TypeKey", "p": {"keyCode": last}}]
                + [{"dev": kb, "m": "ReleaseKey", "p": {"keyCode": c}} for c in reversed(mods)])

    x, y = kw.get("x"), kw.get("y")
    pos = [move(x, y)] if x is not None and y is not None else []
    btn_name = {"right_click": "right", "middle_click": "middle"}.get(action, kw.get("button") or "left")
    btn = _MOUSE_BUTTONS.get(btn_name)
    if btn is None:
        return f"unsupported mouse button {btn_name!r}"

    if action in ("click", "double_click", "triple_click", "right_click", "middle_click"):
        clicks = {"double_click": 2, "triple_click": 3}.get(action, 1)
        steps = list(pos)
        for i in range(clicks):
            if i:
                steps.append({"sleep": 40})
            steps += [button(btn, True), button(btn, False)]
        return steps
    if action == "mouse_move":
        return pos or "mouse_move requires coordinate"
    if action in ("mouse_down", "mouse_up"):
        return pos + [button(btn, action == "mouse_down")]
    if action == "scroll":
        amount = int(kw.get("amount") or 3)
        direction = str(kw.get("direction") or "down").lower()
        if direction not in ("up", "down"):
            return "Hyper-V synthetic mouse only scrolls up/down"
        delta = 120 * amount * (1 if direction == "up" else -1)
        return pos + [{"dev": mouse, "m": "SetScrollPosition", "p": {"scrollPositionDelta": delta}}]
    if action == "drag":
        if not kw.get("from_xy") or not kw.get("to_xy"):
            return "drag requires from and to coordinates"
        (fx, fy), (tx, ty) = kw["from_xy"], kw["to_xy"]
        steps = [move(fx, fy), button(btn, True)]
        for i in range(1, 6):
            steps += [{"sleep": 15}, move(fx + (tx - fx) * i / 5, fy + (ty - fy) * i / 5)]
        return steps + [button(btn, False)]
    return f"Unsupported input action: {action}"


def _rgb565_to_png_bytes(data: bytes, width: int, height: int) -> bytes:
    """Convert Hyper-V's raw little-endian RGB565 thumbnail into PNG bytes."""
    import io
    from PIL import Image

    img = Image.frombuffer("RGB", (width, height), data, "raw", "BGR;16", 0, 1)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# QEMU / KVM / libvirt Provider
# ---------------------------------------------------------------------------


class QemuLibvirtProvider(BaseVMProvider):
    """QEMU/KVM provider using virsh CLI (Linux and cross-platform)."""

    def is_available(self) -> bool:
        return bool(shutil.which("virsh"))

    def list_vms(self) -> List[VMInfo]:
        code, out, _ = _run_subprocess(["virsh", "list", "--all"], timeout=10.0)
        if code != 0 or not out:
            return []
        vms: List[VMInfo] = []
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith("---") or line.startswith("Id"):
                continue
            parts = line.split(maxsplit=2)
            if len(parts) >= 3:
                name = parts[1]
                state_str = parts[2].lower()
                state = "running" if "running" in state_str else ("paused" if "paused" in state_str else "stopped")
                os_type = "windows" if "win" in name.lower() else "linux"
                vms.append(VMInfo(name=name, vm_type="qemu", os_type=os_type, state=state))
        return vms

    def get_status(self, name: str, config: Optional[Dict[str, Any]] = None) -> Optional[VMInfo]:
        code, out, _ = _run_subprocess(["virsh", "dominfo", name], timeout=10.0)
        if code != 0:
            return None
        state = "unknown"
        mem = 0
        cpus = 0
        for line in out.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                k = k.strip().lower()
                v = v.strip().lower()
                if k == "state":
                    state = "running" if "running" in v else ("paused" if "paused" in v else "stopped")
                elif k == "cpu(s)":
                    try:
                        cpus = int(v)
                    except ValueError:
                        pass
                elif k == "used memory" or k == "max memory":
                    try:
                        mem = int(v.split()[0]) // 1024
                    except Exception:
                        pass
        return VMInfo(
            name=name,
            vm_type="qemu",
            os_type="windows" if "win" in name.lower() else "linux",
            state=state,
            cpu_count=cpus or None,
            memory_mb=mem or None,
        )

    def start(self, name: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        code, out, err = _run_subprocess(["virsh", "start", name], timeout=20.0)
        return {"ok": code == 0, "message": out or err}

    def stop(self, name: str, force: bool = False, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        cmd = ["virsh", "destroy" if force else "shutdown", name]
        code, out, err = _run_subprocess(cmd, timeout=30.0)
        return {"ok": code == 0, "message": out or err}

    def restart(self, name: str, force: bool = False, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        cmd = ["virsh", "reset" if force else "reboot", name]
        code, out, err = _run_subprocess(cmd, timeout=30.0)
        return {"ok": code == 0, "message": out or err}

    def pause(self, name: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        code, out, err = _run_subprocess(["virsh", "suspend", name], timeout=15.0)
        return {"ok": code == 0, "message": out or err}

    def resume(self, name: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        code, out, err = _run_subprocess(["virsh", "resume", name], timeout=15.0)
        return {"ok": code == 0, "message": out or err}

    def snapshot(
        self,
        name: str,
        operation: str,
        snapshot_name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        op = operation.lower().strip()
        if op == "create":
            snap = snapshot_name or f"snap_{int(time.time())}"
            code, out, err = _run_subprocess(["virsh", "snapshot-create-as", name, snap], timeout=30.0)
            return {"ok": code == 0, "snapshot_name": snap, "message": out or err}
        elif op == "restore":
            if not snapshot_name:
                return {"ok": False, "error": "snapshot_name required"}
            code, out, err = _run_subprocess(["virsh", "snapshot-revert", name, snapshot_name], timeout=40.0)
            return {"ok": code == 0, "message": out or err}
        elif op == "delete":
            if not snapshot_name:
                return {"ok": False, "error": "snapshot_name required"}
            code, out, err = _run_subprocess(["virsh", "snapshot-delete", name, snapshot_name], timeout=25.0)
            return {"ok": code == 0, "message": out or err}
        elif op == "list":
            code, out, err = _run_subprocess(["virsh", "snapshot-list", name], timeout=15.0)
            snaps = []
            if code == 0:
                for line in out.splitlines():
                    parts = line.strip().split()
                    if parts and not parts[0].startswith("-") and parts[0] != "Name":
                        snaps.append({"name": parts[0], "created_at": " ".join(parts[1:3]) if len(parts) >= 3 else ""})
            return {"ok": code == 0, "snapshots": snaps, "count": len(snaps)}
        return {"ok": False, "error": f"Unknown snapshot operation: {operation}"}

    def capture_screen(self, name: str, config: Optional[Dict[str, Any]] = None) -> Tuple[Optional[str], Optional[str]]:
        with tempfile.NamedTemporaryFile(suffix=".ppm", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            code, _, err = _run_subprocess(["virsh", "screenshot", name, tmp_path], timeout=15.0)
            if code != 0 or not os.path.exists(tmp_path):
                return None, f"virsh screenshot failed: {err}"
            with open(tmp_path, "rb") as f:
                ppm_data = f.read()
            png_bytes = _convert_ppm_to_png_bytes(ppm_data)
            if png_bytes:
                return base64.b64encode(png_bytes).decode("ascii"), None
            return None, "Failed converting PPM to PNG"
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# VMware Provider
# ---------------------------------------------------------------------------


class VMwareProvider(BaseVMProvider):
    """VMware Workstation / Fusion provider using vmrun."""

    def __init__(self) -> None:
        self._vmrun_bin = self._find_vmrun()

    def _find_vmrun(self) -> Optional[str]:
        w = shutil.which("vmrun") or shutil.which("vmrun.exe")
        if w:
            return w
        candidates = [
            r"C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe",
            r"C:\Program Files\VMware\VMware Workstation\vmrun.exe",
            "/Applications/VMware Fusion.app/Contents/Library/vmrun",
            "/usr/bin/vmrun",
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return None

    def is_available(self) -> bool:
        return bool(self._vmrun_bin)

    def _cmd(self, args: List[str], timeout: float = 30.0) -> Tuple[int, str, str]:
        if not self._vmrun_bin:
            return -1, "", "vmrun not found"
        return _run_subprocess([self._vmrun_bin, "-T", "ws"] + args, timeout=timeout)

    def list_vms(self) -> List[VMInfo]:
        code, out, _ = self._cmd(["list"])
        if code != 0:
            return []
        vms = []
        for line in out.splitlines()[1:]:
            line = line.strip()
            if line and line.endswith(".vmx"):
                name = Path(line).stem
                os_type = "windows" if "win" in name.lower() else "linux"
                vms.append(VMInfo(name=name, vm_type="vmware", os_type=os_type, state="running", extra={"vmx": line}))
        return vms

    def start(self, name: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        vmx = (config or {}).get("vmx_path") or name
        code, out, err = self._cmd(["start", vmx, "nogui"])
        return {"ok": code == 0, "message": out or err}

    def stop(self, name: str, force: bool = False, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        vmx = (config or {}).get("vmx_path") or name
        code, out, err = self._cmd(["stop", vmx, "hard" if force else "soft"])
        return {"ok": code == 0, "message": out or err}

    def restart(self, name: str, force: bool = False, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        vmx = (config or {}).get("vmx_path") or name
        code, out, err = self._cmd(["reset", vmx, "hard" if force else "soft"])
        return {"ok": code == 0, "message": out or err}

    def snapshot(
        self,
        name: str,
        operation: str,
        snapshot_name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        vmx = (config or {}).get("vmx_path") or name
        op = operation.lower().strip()
        if op == "create":
            snap = snapshot_name or f"snap_{int(time.time())}"
            code, out, err = self._cmd(["snapshot", vmx, snap])
            return {"ok": code == 0, "snapshot_name": snap, "message": out or err}
        elif op == "restore":
            code, out, err = self._cmd(["revertToSnapshot", vmx, snapshot_name or ""])
            return {"ok": code == 0, "message": out or err}
        elif op == "delete":
            code, out, err = self._cmd(["deleteSnapshot", vmx, snapshot_name or ""])
            return {"ok": code == 0, "message": out or err}
        elif op == "list":
            code, out, err = self._cmd(["listSnapshots", vmx])
            snaps = [{"name": s.strip()} for s in out.splitlines()[1:] if s.strip()] if code == 0 else []
            return {"ok": code == 0, "snapshots": snaps, "count": len(snaps)}
        return {"ok": False, "error": f"Unknown snapshot operation: {operation}"}

    def capture_screen(self, name: str, config: Optional[Dict[str, Any]] = None) -> Tuple[Optional[str], Optional[str]]:
        vmx = (config or {}).get("vmx_path") or name
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            code, _, err = self._cmd(["captureScreen", vmx, tmp_path], timeout=15.0)
            if code == 0 and os.path.exists(tmp_path):
                with open(tmp_path, "rb") as f:
                    return base64.b64encode(f.read()).decode("ascii"), None
            return None, f"VMware captureScreen failed: {err}"
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# VirtualBox Provider
# ---------------------------------------------------------------------------


class VirtualBoxProvider(BaseVMProvider):
    """VirtualBox provider using VBoxManage."""

    def __init__(self) -> None:
        self._vbox_bin = self._find_vbox()

    def _find_vbox(self) -> Optional[str]:
        w = shutil.which("VBoxManage") or shutil.which("VBoxManage.exe")
        if w:
            return w
        cand = r"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"
        return cand if os.path.exists(cand) else None

    def is_available(self) -> bool:
        return bool(self._vbox_bin)

    def _cmd(self, args: List[str], timeout: float = 30.0) -> Tuple[int, str, str]:
        if not self._vbox_bin:
            return -1, "", "VBoxManage not found"
        return _run_subprocess([self._vbox_bin] + args, timeout=timeout)

    def list_vms(self) -> List[VMInfo]:
        code, out, _ = self._cmd(["list", "vms"])
        if code != 0:
            return []
        vms = []
        for line in out.splitlines():
            line = line.strip()
            match = re.match(r'^"([^"]+)"\s+\{([^}]+)\}', line)
            if match:
                name = match.group(1)
                os_type = "windows" if "win" in name.lower() else "linux"
                vms.append(VMInfo(name=name, vm_type="virtualbox", os_type=os_type, state="unknown", extra={"uuid": match.group(2)}))
        return vms

    def start(self, name: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        code, out, err = self._cmd(["startvm", name, "--type", "headless"])
        return {"ok": code == 0, "message": out or err}

    def stop(self, name: str, force: bool = False, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        code, out, err = self._cmd(["controlvm", name, "poweroff" if force else "acpipowerbutton"])
        return {"ok": code == 0, "message": out or err}

    def restart(self, name: str, force: bool = False, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        code, out, err = self._cmd(["controlvm", name, "reset"])
        return {"ok": code == 0, "message": out or err}

    def capture_screen(self, name: str, config: Optional[Dict[str, Any]] = None) -> Tuple[Optional[str], Optional[str]]:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            code, _, err = self._cmd(["controlvm", name, "screenshotpng", tmp_path], timeout=15.0)
            if code == 0 and os.path.exists(tmp_path):
                with open(tmp_path, "rb") as f:
                    return base64.b64encode(f.read()).decode("ascii"), None
            return None, f"VirtualBox screenshot failed: {err}"
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# WSL / WSL2 Provider (Windows Subsystem for Linux)
# ---------------------------------------------------------------------------


class WSLProvider(BaseVMProvider):
    """Windows Subsystem for Linux (WSL2) provider."""

    def is_available(self) -> bool:
        if sys.platform != "win32":
            return False
        return bool(shutil.which("wsl") or shutil.which("wsl.exe"))

    def list_vms(self) -> List[VMInfo]:
        try:
            proc = subprocess.run(
                ["wsl.exe", "-l", "-v"],
                capture_output=True,
                text=True,
                encoding="utf-16le",
                errors="replace",
                timeout=8.0,
            )
            if proc.returncode != 0 or not proc.stdout:
                return []
            vms = []
            for line in proc.stdout.splitlines()[1:]:
                line = line.strip().replace("*", "").strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    name = parts[0]
                    state_str = parts[1].lower()
                    state = "running" if "running" in state_str else "stopped"
                    version = parts[2] if len(parts) >= 3 else "2"
                    vms.append(
                        VMInfo(
                            name=name,
                            vm_type="wsl2",
                            os_type="linux",
                            state=state,
                            notes=f"WSL version {version}",
                            extra={"wsl_version": version},
                        )
                    )
            return vms
        except Exception as exc:
            logger.debug("Failed listing WSL distros: %s", exc)
            return []

    def get_status(self, name: str, config: Optional[Dict[str, Any]] = None) -> Optional[VMInfo]:
        vms = self.list_vms()
        for v in vms:
            if v.name.lower() == name.lower():
                return v
        return None

    def start(self, name: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        code, out, err = _run_subprocess(["wsl.exe", "-d", name, "--", "echo", "online"], timeout=15.0)
        return {"ok": code == 0, "message": f"WSL distro '{name}' started" if code == 0 else err}

    def stop(self, name: str, force: bool = False, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        code, out, err = _run_subprocess(["wsl.exe", "--terminate", name], timeout=15.0)
        return {"ok": code == 0, "message": f"WSL distro '{name}' terminated" if code == 0 else err}

    def restart(self, name: str, force: bool = False, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.stop(name, force=True, config=config)
        return self.start(name, config=config)

    def execute(
        self,
        name: str,
        command: str,
        timeout: float = 60.0,
        config: Optional[Dict[str, Any]] = None,
    ) -> VMExecutionResult:
        start_t = time.time()
        cmd = ["wsl.exe", "-d", name, "--", "sh", "-c", command]
        code, out, err = _run_subprocess(cmd, timeout=timeout)
        duration = time.time() - start_t
        return VMExecutionResult(exit_code=code, stdout=out, stderr=err, duration_seconds=round(duration, 3))

    def transfer_file(
        self,
        name: str,
        source: str,
        dest: str,
        direction: str = "upload",
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if direction == "upload":
            script = 'cp -- "$(wslpath -u "$1")" "$2"'
        else:
            script = 'cp -- "$1" "$(wslpath -u "$2")"'
        cmd = ["wsl.exe", "-d", name, "--", "sh", "-c", script, "sh", source, dest]
        code, out, err = _run_subprocess(cmd, timeout=30.0)
        return {"ok": code == 0, "message": out or ("Transferred" if code == 0 else err)}

    def capture_screen(self, name: str, config: Optional[Dict[str, Any]] = None) -> Tuple[Optional[str], Optional[str]]:
        cmd = "scrot -z /tmp/wsl_cap.png && base64 -w 0 /tmp/wsl_cap.png && rm -f /tmp/wsl_cap.png"
        res = self.execute(name, cmd, timeout=15.0)
        if res.exit_code == 0 and res.stdout.strip():
            return res.stdout.strip(), None
        return None, "No active graphical desktop (scrot) found inside WSL distro"

    def send_input(
        self,
        name: str,
        action: str,
        config: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        if action == "type":
            text = kwargs.get("text", "")
            return self.execute(name, f"xdotool type --delay 30 {shlex.quote(text)}").to_dict()
        elif action == "key":
            keys = kwargs.get("keys", "")
            return self.execute(name, f"xdotool key {shlex.quote(keys)}").to_dict()
        elif action == "click":
            x = kwargs.get("x", 0)
            y = kwargs.get("y", 0)
            return self.execute(name, f"xdotool mousemove {x} {y} click 1").to_dict()
        return {"ok": False, "error": f"Unsupported action {action} in WSL"}


# ---------------------------------------------------------------------------
# Remote VPS Provider (Linux via SSH, Windows via WinRM / OpenSSH)
# ---------------------------------------------------------------------------


# SSH/WinRM logons run outside the interactive desktop (session 0), so there is
# no screen to capture or inject into from them.
_WINDOWS_VPS_GUI_ERROR = (
    "GUI capture/input is not supported on Windows VPS targets over SSH: remote "
    "sessions have no interactive desktop. Use vm_exec for commands, or run the "
    "guest under a local hypervisor (Hyper-V/QEMU/VMware/VirtualBox) for GUI control."
)


class RemoteVPSProvider(BaseVMProvider):
    """Remote VPS management over SSH (Linux) or WinRM/OpenSSH (Windows)."""

    def is_available(self) -> bool:
        return bool(shutil.which("ssh") or shutil.which("ssh.exe"))

    def _build_ssh_cmd(self, config: Dict[str, Any], remote_cmd: str) -> List[str]:
        host = config.get("host", "localhost")
        port = str(config.get("port", 22))
        user = config.get("user", "root")
        key_path = config.get("key_path")

        cmd = [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=10",
            "-p", port,
        ]
        if key_path and os.path.exists(os.path.expanduser(key_path)):
            cmd.extend(["-i", os.path.expanduser(key_path)])
        cmd.append(f"{user}@{host}")
        cmd.append(remote_cmd)
        return cmd

    def get_status(self, name: str, config: Optional[Dict[str, Any]] = None) -> Optional[VMInfo]:
        cfg = config or {}
        os_type = cfg.get("os_type", "linux").lower()
        host = cfg.get("host", "")
        port = cfg.get("port", 22)
        user = cfg.get("user", "")

        probe_cmd = "echo PONG && uname -a && uptime && free -m" if os_type == "linux" else "echo PONG"
        cmd = self._build_ssh_cmd(cfg, probe_cmd)
        code, out, _ = _run_subprocess(cmd, timeout=12.0)

        state = "running" if code == 0 and "PONG" in out else "stopped"
        return VMInfo(
            name=name,
            vm_type=f"vps_{'ssh' if os_type == 'linux' else 'winrm'}",
            os_type=os_type,
            state=state,
            host=host,
            port=port,
            user=user,
            notes=cfg.get("notes", ""),
        )

    def start(self, name: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        st = self.get_status(name, config)
        if st and st.state == "running":
            return {"ok": True, "message": f"VPS '{name}' is online and reachable"}
        return {"ok": False, "error": f"VPS '{name}' is unreachable via remote connection"}

    def stop(self, name: str, force: bool = False, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        cfg = config or {}
        os_type = cfg.get("os_type", "linux").lower()
        cmd_str = "sudo poweroff" if os_type == "linux" else "Stop-Computer -Force"
        cmd = self._build_ssh_cmd(cfg, cmd_str)
        code, out, err = _run_subprocess(cmd, timeout=15.0)
        return {"ok": code == 0 or "Closed connection" in err, "message": "Shutdown signal sent to VPS"}

    def restart(self, name: str, force: bool = False, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        cfg = config or {}
        os_type = cfg.get("os_type", "linux").lower()
        cmd_str = "sudo reboot" if os_type == "linux" else "Restart-Computer -Force"
        cmd = self._build_ssh_cmd(cfg, cmd_str)
        code, out, err = _run_subprocess(cmd, timeout=15.0)
        return {"ok": code == 0 or "Closed connection" in err, "message": "Reboot signal sent to VPS"}

    def execute(
        self,
        name: str,
        command: str,
        timeout: float = 60.0,
        config: Optional[Dict[str, Any]] = None,
    ) -> VMExecutionResult:
        cfg = config or {}
        cmd = self._build_ssh_cmd(cfg, command)
        start_t = time.time()
        code, out, err = _run_subprocess(cmd, timeout=timeout)
        duration = time.time() - start_t
        return VMExecutionResult(exit_code=code, stdout=out, stderr=err, duration_seconds=round(duration, 3))

    def transfer_file(
        self,
        name: str,
        source: str,
        dest: str,
        direction: str = "upload",
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        cfg = config or {}
        host = cfg.get("host", "localhost")
        port = str(cfg.get("port", 22))
        user = cfg.get("user", "root")
        key_path = cfg.get("key_path")

        scp_bin = shutil.which("scp") or shutil.which("scp.exe") or "scp"
        scp_cmd = [
            scp_bin,
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-P", port,
        ]
        if key_path and os.path.exists(os.path.expanduser(key_path)):
            scp_cmd.extend(["-i", os.path.expanduser(key_path)])

        if direction == "upload":
            scp_cmd.extend([source, f"{user}@{host}:{dest}"])
        else:
            scp_cmd.extend([f"{user}@{host}:{source}", dest])

        code, out, err = _run_subprocess(scp_cmd, timeout=120.0)
        return {"ok": code == 0, "message": out or ("Transferred" if code == 0 else err)}

    def capture_screen(self, name: str, config: Optional[Dict[str, Any]] = None) -> Tuple[Optional[str], Optional[str]]:
        cfg = config or {}
        os_type = cfg.get("os_type", "linux").lower()

        if os_type == "linux":
            # Try scrot, import, or maim on Linux X11/Wayland display
            cmd = "DISPLAY=:0 scrot -z /tmp/screen.png && base64 -w 0 /tmp/screen.png && rm -f /tmp/screen.png"
            res = self.execute(name, cmd, timeout=20.0, config=cfg)
            if res.exit_code == 0 and res.stdout.strip():
                return res.stdout.strip(), None
            # Fallback to ImageMagick import
            cmd2 = "DISPLAY=:0 import -window root /tmp/screen.png && base64 -w 0 /tmp/screen.png && rm -f /tmp/screen.png"
            res2 = self.execute(name, cmd2, timeout=20.0, config=cfg)
            if res2.exit_code == 0 and res2.stdout.strip():
                return res2.stdout.strip(), None
            return None, f"Linux VPS screen capture failed: {res.stderr or res2.stderr or 'No capture utility installed (scrot/import)'}"
        return None, _WINDOWS_VPS_GUI_ERROR

    def send_input(
        self,
        name: str,
        action: str,
        config: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        cfg = config or {}
        os_type = cfg.get("os_type", "linux").lower()

        if os_type == "linux":
            if action == "type":
                text = kwargs.get("text", "")
                cmd = f"DISPLAY=:0 xdotool type --delay 30 {shlex.quote(text)}"
                res = self.execute(name, cmd, timeout=10.0, config=cfg)
                return {"ok": res.exit_code == 0, "message": res.stdout or res.stderr}
            elif action == "key":
                keys = kwargs.get("keys", "")
                cmd = f"DISPLAY=:0 xdotool key {shlex.quote(keys)}"
                res = self.execute(name, cmd, timeout=10.0, config=cfg)
                return {"ok": res.exit_code == 0, "message": res.stdout or res.stderr}
            elif action in ("click", "double_click", "right_click", "middle_click"):
                x = kwargs.get("x", 0)
                y = kwargs.get("y", 0)
                btn = 1 if action == "click" else (3 if action == "right_click" else (2 if action == "middle_click" else 1))
                repeat = "--repeat 2 --delay 50 " if action == "double_click" else ""
                cmd = f"DISPLAY=:0 xdotool mousemove {x} {y} click {repeat}{btn}"
                res = self.execute(name, cmd, timeout=10.0, config=cfg)
                return {"ok": res.exit_code == 0, "message": res.stdout or res.stderr}
            elif action == "scroll":
                direction = str(kwargs.get("direction", "down")).lower()
                amount = int(kwargs.get("amount", 3))
                btn = 4 if direction == "up" else 5
                cmd = f"DISPLAY=:0 xdotool click --repeat {amount} {btn}"
                res = self.execute(name, cmd, timeout=10.0, config=cfg)
                return {"ok": res.exit_code == 0, "message": res.stdout or res.stderr}
            elif action == "drag":
                fx, fy = kwargs.get("from_xy") or (0, 0)
                tx, ty = kwargs.get("to_xy") or (0, 0)
                cmd = f"DISPLAY=:0 xdotool mousemove {fx} {fy} mousedown 1 mousemove {tx} {ty} mouseup 1"
                res = self.execute(name, cmd, timeout=10.0, config=cfg)
                return {"ok": res.exit_code == 0, "message": res.stdout or res.stderr}
            elif action == "mouse_move":
                x = kwargs.get("x", 0)
                y = kwargs.get("y", 0)
                cmd = f"DISPLAY=:0 xdotool mousemove {x} {y}"
                res = self.execute(name, cmd, timeout=10.0, config=cfg)
                return {"ok": res.exit_code == 0, "message": res.stdout or res.stderr}
            elif action in ("mouse_down", "mouse_up"):
                btn = 1 if kwargs.get("button", "left") == "left" else (3 if kwargs.get("button") == "right" else 2)
                verb = "mousedown" if action == "mouse_down" else "mouseup"
                x = kwargs.get("x")
                y = kwargs.get("y")
                move = f"mousemove {x} {y} " if x is not None and y is not None else ""
                cmd = f"DISPLAY=:0 xdotool {move}{verb} {btn}"
                res = self.execute(name, cmd, timeout=10.0, config=cfg)
                return {"ok": res.exit_code == 0, "message": res.stdout or res.stderr}

        elif os_type == "windows":
            return {"ok": False, "error": _WINDOWS_VPS_GUI_ERROR}

        return {"ok": False, "error": f"send_input not supported for {os_type} VPS or action {action}"}


# ---------------------------------------------------------------------------
# Central VM / VPS Manager & Inventory
# ---------------------------------------------------------------------------


class VMManager:
    """Central orchestration manager for virtual machines and remote VPSes."""

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        self._lock = threading.Lock()
        self._storage_path = storage_path or self._default_storage_path()
        self._unattended_enabled: bool = False
        self._unattended_target: Optional[str] = None
        self._scales: Dict[str, Tuple[float, float]] = {}
        self._dimensions: Dict[str, Tuple[int, int]] = {}
        self._last_cursor_pos: Dict[str, Tuple[int, int]] = {}
        self._providers: Dict[str, BaseVMProvider] = {
            "hyperv": HyperVProvider(),
            "wsl": WSLProvider(),
            "qemu": QemuLibvirtProvider(),
            "vmware": VMwareProvider(),
            "virtualbox": VirtualBoxProvider(),
            "vps": RemoteVPSProvider(),
        }

    @staticmethod
    def _default_storage_path() -> Path:
        try:
            from jettstui_constants import get_jettstui_home

            return Path(get_jettstui_home()) / "vms.json"
        except Exception:
            return Path.home() / ".jettstui" / "vms.json"

    # -- Unattended Isolation Management ------------------------------------

    def is_unattended_enabled(self) -> bool:
        """Return True if unattended computer use mode is active."""
        if self._unattended_enabled:
            return True
        data = self._load_data()
        return bool(data.get("unattended", {}).get("enabled", False))

    def get_active_unattended_target(self) -> Optional[str]:
        """Find the active or best running VM/VPS target for unattended computer use."""
        if self._unattended_target:
            return self._unattended_target

        data = self._load_data()
        saved_target = data.get("unattended", {}).get("target")
        if saved_target and saved_target != "auto":
            self._unattended_target = saved_target
            return saved_target

        # Auto-discover first running VM
        vms = self.list_vms()
        running_vms = [v for v in vms if v.get("state") == "running"]
        if running_vms:
            target_name = running_vms[0]["name"]
            self._unattended_target = target_name
            return target_name

        # If none running, check if any registered VM exists
        registered = self._load_inventory()
        if registered:
            target_name = next(iter(registered.keys()))
            self._unattended_target = target_name
            return target_name

        return None

    def set_unattended(self, target: Optional[str] = None, enabled: bool = True) -> Dict[str, Any]:
        """Configure unattended computer use mode and isolation target."""
        self._unattended_enabled = enabled
        if target:
            self._unattended_target = target if target.lower() != "auto" else self.get_active_unattended_target()
        elif enabled and not self._unattended_target:
            self._unattended_target = self.get_active_unattended_target()

        # Persist unattended state to disk
        data = self._load_data()
        data["unattended"] = {
            "enabled": enabled,
            "target": self._unattended_target or "auto",
            "updated_at": time.time(),
        }
        self._save_data(data)

        status_msg = (
            f"Unattended computer use enabled on target '{self._unattended_target}'. "
            "Host PC input, mouse, and keyboard are completely protected and free for your use."
            if enabled
            else "Unattended computer use disabled."
        )
        return {
            "ok": True,
            "unattended_enabled": enabled,
            "target": self._unattended_target,
            "message": status_msg,
        }

    def get_unattended_status(self) -> Dict[str, Any]:
        """Return isolation status and current target health for unattended computer use."""
        enabled = self.is_unattended_enabled()
        active = self.get_active_unattended_target()
        st = self.get_status(active) if active else None
        state = (st.get("status") or {}).get("state", "unknown") if st and st.get("ok") else "stopped"
        vm_type = (st.get("status") or {}).get("vm_type", "unknown") if st and st.get("ok") else "vm"

        return {
            "ok": True,
            "unattended_enabled": enabled,
            "active_target": active,
            "target_state": state,
            "isolation_type": f"{vm_type}_hardware_boundary",
            "host_input_protected": True,
            "message": (
                f"Unattended computer use is active on '{active}' (state: {state}). "
                "All clicks, typing, and captures run inside the VM environment without "
                "stealing focus or moving the host cursor."
                if active
                else "No unattended VM target active. Use 'unattended_set' or 'vm_start' to activate one."
            ),
        }

    # -- Inventory Persistence ----------------------------------------------

    def _load_data(self) -> Dict[str, Any]:
        with self._lock:
            if not self._storage_path.exists():
                return {}
            try:
                with open(self._storage_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as exc:
                logger.warning("Failed loading VM inventory from %s: %s", self._storage_path, exc)
                return {}

    def _save_data(self, data: Dict[str, Any]) -> None:
        with self._lock:
            try:
                self._storage_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self._storage_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception as exc:
                logger.error("Failed saving VM inventory to %s: %s", self._storage_path, exc)

    def _load_inventory(self) -> Dict[str, Dict[str, Any]]:
        return self._load_data().get("vms", {})

    def _save_inventory(self, inventory: Dict[str, Dict[str, Any]]) -> None:
        data = self._load_data()
        data["vms"] = inventory
        data["version"] = 1
        self._save_data(data)

    def register_vm(
        self,
        name: str,
        vm_type: str,
        os_type: str = "linux",
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password_env: Optional[str] = None,
        key_path: Optional[str] = None,
        vmx_path: Optional[str] = None,
        notes: str = "",
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Register a new VM or remote VPS definition into the persistent inventory.

        Passwords are never stored: ``password_env`` names the env var (set in
        ``.env``) that holds it, resolved only when a provider needs it.
        """
        inv = self._load_inventory()
        inv[name] = {
            "name": name,
            "vm_type": vm_type,
            "os_type": os_type.lower(),
            "host": host,
            "port": port or (22 if "ssh" in vm_type or vm_type == "qemu" else (5985 if "winrm" in vm_type else None)),
            "user": user,
            "password_env": password_env,
            "key_path": key_path,
            "vmx_path": vmx_path,
            "notes": notes,
            "extra": extra or {},
            "registered_at": time.time(),
        }
        self._save_inventory(inv)
        return {"ok": True, "message": f"VM/VPS '{name}' registered successfully"}

    def unregister_vm(self, name: str) -> Dict[str, Any]:
        """Remove a VM or VPS from the registered inventory."""
        inv = self._load_inventory()
        if name in inv:
            del inv[name]
            self._save_inventory(inv)
            return {"ok": True, "message": f"VM/VPS '{name}' unregistered"}
        return {"ok": False, "error": f"VM/VPS '{name}' not found in inventory"}

    def get_registered_vm(self, name: str) -> Optional[Dict[str, Any]]:
        inv = self._load_inventory()
        return inv.get(name)

    # -- Resolution & Routing -----------------------------------------------

    def _resolve_target(self, name: str) -> Tuple[Optional[BaseVMProvider], Optional[Dict[str, Any]]]:
        """Resolve a VM/VPS name to a provider and its configuration."""
        reg = self.get_registered_vm(name)
        if reg:
            reg = dict(reg)
            if reg.get("password_env"):
                reg["password"] = os.environ.get(reg["password_env"])
            elif reg.get("password"):
                logger.warning(
                    "VM '%s' has a plaintext password in %s; move it to .env and re-register with --password-env",
                    name, self._storage_path,
                )
            vm_type = reg.get("vm_type", "")
            if vm_type in ("vps_ssh", "vps_winrm", "vps"):
                return self._providers["vps"], reg
            if vm_type in self._providers:
                return self._providers[vm_type], reg

        # If not registered or type auto, check local hypervisors
        for prov_key in ("hyperv", "wsl", "qemu", "vmware", "virtualbox"):
            prov = self._providers[prov_key]
            if prov.is_available():
                for vm in prov.list_vms():
                    if vm.name.lower() == name.lower():
                        return prov, reg or vm.to_dict()

        # Fallback to Hyper-V if on Windows, else QEMU
        default_prov = self._providers["hyperv"] if sys.platform == "win32" else self._providers["qemu"]
        return default_prov, reg

    # -- Unified Operations -------------------------------------------------

    def list_vms(self, include_discovered: bool = True) -> List[Dict[str, Any]]:
        """List all registered and discovered virtual machines and VPSes."""
        registered = self._load_inventory()
        results: Dict[str, Dict[str, Any]] = {}

        # 1. Include registered VPSes / VMs
        for name, item in registered.items():
            results[name] = {
                "name": name,
                "vm_type": item.get("vm_type", "unknown"),
                "os_type": item.get("os_type", "unknown"),
                "state": "configured",
                "host": item.get("host"),
                "port": item.get("port"),
                "user": item.get("user"),
                "notes": item.get("notes", ""),
                "registered": True,
            }

        # 2. Auto-discover from available local hypervisors
        if include_discovered:
            for prov_key in ("hyperv", "wsl", "qemu", "vmware", "virtualbox"):
                prov = self._providers.get(prov_key)
                if prov and prov.is_available():
                    try:
                        for vm in prov.list_vms():
                            dict_rep = vm.to_dict()
                            dict_rep["registered"] = vm.name in results
                            if vm.name in results:
                                results[vm.name].update(dict_rep)
                                results[vm.name]["registered"] = True
                            else:
                                results[vm.name] = dict_rep
                    except Exception as exc:
                        logger.debug("Error discovering from %s: %s", prov_key, exc)

        return list(results.values())

    def get_status(self, name: str) -> Dict[str, Any]:
        prov, cfg = self._resolve_target(name)
        if not prov:
            return {"ok": False, "error": f"Target '{name}' could not be resolved"}
        info = prov.get_status(name, cfg)
        if info:
            return {"ok": True, "status": info.to_dict()}
        return {"ok": False, "error": f"Could not retrieve status for '{name}'"}

    def start_vm(self, name: str) -> Dict[str, Any]:
        prov, cfg = self._resolve_target(name)
        if not prov:
            return {"ok": False, "error": f"Target '{name}' could not be resolved"}
        return prov.start(name, cfg)

    def stop_vm(self, name: str, force: bool = False) -> Dict[str, Any]:
        prov, cfg = self._resolve_target(name)
        if not prov:
            return {"ok": False, "error": f"Target '{name}' could not be resolved"}
        return prov.stop(name, force=force, config=cfg)

    def restart_vm(self, name: str, force: bool = False) -> Dict[str, Any]:
        prov, cfg = self._resolve_target(name)
        if not prov:
            return {"ok": False, "error": f"Target '{name}' could not be resolved"}
        return prov.restart(name, force=force, config=cfg)

    def pause_vm(self, name: str) -> Dict[str, Any]:
        prov, cfg = self._resolve_target(name)
        if not prov:
            return {"ok": False, "error": f"Target '{name}' could not be resolved"}
        return prov.pause(name, cfg)

    def resume_vm(self, name: str) -> Dict[str, Any]:
        prov, cfg = self._resolve_target(name)
        if not prov:
            return {"ok": False, "error": f"Target '{name}' could not be resolved"}
        return prov.resume(name, cfg)

    def snapshot(self, name: str, operation: str, snapshot_name: Optional[str] = None) -> Dict[str, Any]:
        prov, cfg = self._resolve_target(name)
        if not prov:
            return {"ok": False, "error": f"Target '{name}' could not be resolved"}
        return prov.snapshot(name, operation, snapshot_name=snapshot_name, config=cfg)

    def execute_in_vm(self, name: str, command: str, timeout: float = 60.0) -> VMExecutionResult:
        prov, cfg = self._resolve_target(name)
        if not prov:
            return VMExecutionResult(exit_code=-1, stdout="", stderr=f"Target '{name}' not found")
        return prov.execute(name, command, timeout=timeout, config=cfg)

    def transfer_file(
        self,
        name: str,
        source: str,
        dest: str,
        direction: str = "upload",
    ) -> Dict[str, Any]:
        prov, cfg = self._resolve_target(name)
        if not prov:
            return {"ok": False, "error": f"Target '{name}' not found"}
        return prov.transfer_file(name, source, dest, direction=direction, config=cfg)

    def capture_screen(self, name: str, max_width: int = 1280) -> Tuple[Optional[str], Optional[str], int, int]:
        """Capture screen from VM and scale to max_width while saving coordinate aspect ratio."""
        prov, cfg = self._resolve_target(name)
        if not prov:
            return None, f"Target '{name}' not found", 1280, 720
        b64_raw, err = prov.capture_screen(name, cfg)
        if err or not b64_raw:
            return None, err, 1280, 720

        try:
            raw_bytes = base64.b64decode(b64_raw)
            import io
            from PIL import Image

            img = Image.open(io.BytesIO(raw_bytes))
            orig_w, orig_h = img.size
            if max_width > 0 and orig_w > max_width:
                scaled_w = max_width
                scaled_h = int(round(orig_h * (max_width / orig_w)))
                img = img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                scaled_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                self._scales[name] = (orig_w / scaled_w, orig_h / scaled_h)
                self._dimensions[name] = (scaled_w, scaled_h)
                return scaled_b64, None, scaled_w, scaled_h
            else:
                self._scales[name] = (1.0, 1.0)
                self._dimensions[name] = (orig_w, orig_h)
                return b64_raw, None, orig_w, orig_h
        except Exception as exc:
            logger.debug("Failed parsing/scaling image for %s: %s", name, exc)
            self._scales[name] = (1.0, 1.0)
            self._dimensions[name] = (1280, 720)
            return b64_raw, None, 1280, 720

    def send_input(self, name: str, action: str, **kwargs) -> Dict[str, Any]:
        """Send input into VM with automatic coordinate translation from scaled frame."""
        prov, cfg = self._resolve_target(name)
        if not prov:
            return {"ok": False, "error": f"Target '{name}' not found"}

        scale_x, scale_y = self._scales.get(name, (1.0, 1.0))
        if kwargs.get("x") is not None:
            kwargs["x"] = int(round(kwargs["x"] * scale_x))
        if kwargs.get("y") is not None:
            kwargs["y"] = int(round(kwargs["y"] * scale_y))
        if kwargs.get("from_xy"):
            fx, fy = kwargs["from_xy"]
            kwargs["from_xy"] = (int(round(fx * scale_x)), int(round(fy * scale_y)))
        if kwargs.get("to_xy"):
            tx, ty = kwargs["to_xy"]
            kwargs["to_xy"] = (int(round(tx * scale_x)), int(round(ty * scale_y)))

        if kwargs.get("x") is not None and kwargs.get("y") is not None:
            self._last_cursor_pos[name] = (int(kwargs["x"]), int(kwargs["y"]))

        return prov.send_input(name, action, config=cfg, **kwargs)

    # -- Action Handler for computer_use ------------------------------------

    def handle_action(self, action: str, args: Dict[str, Any]) -> Any:
        """Route tool actions from computer_use to the appropriate VM/VPS method."""
        target = args.get("target") or args.get("vm_name")
        vm_action = (args.get("vm_action") or "").lower().strip()

        # Handle unattended mode controls
        if action == "unattended_set":
            return json.dumps(self.set_unattended(target=args.get("target"), enabled=args.get("enabled", True)))

        if action == "unattended_status":
            return json.dumps(self.get_unattended_status())

        if action == "unattended_stop":
            return json.dumps(self.set_unattended(enabled=False))

        # Auto-resolve target if unattended is requested
        if (args.get("unattended") or self._unattended_enabled) and not target:
            target = self.get_active_unattended_target()

        if action == "vm_list":
            vms = self.list_vms()
            return json.dumps({"ok": True, "vms": vms, "count": len(vms)})

        if not target:
            return json.dumps({"ok": False, "error": f"Action '{action}' requires 'target' or 'vm_name'"})

        if action == "vm_status":
            return json.dumps(self.get_status(target))

        if action == "vm_start":
            return json.dumps(self.start_vm(target))

        if action == "vm_stop":
            force = bool(args.get("force", False))
            return json.dumps(self.stop_vm(target, force=force))

        if action == "vm_restart":
            force = bool(args.get("force", False))
            return json.dumps(self.restart_vm(target, force=force))

        if action == "vm_pause":
            return json.dumps(self.pause_vm(target))

        if action == "vm_resume":
            return json.dumps(self.resume_vm(target))

        if action == "vm_snapshot":
            op = vm_action or "list"
            snap_name = args.get("snapshot_name")
            return json.dumps(self.snapshot(target, op, snapshot_name=snap_name))

        if action == "vm_exec":
            cmd = args.get("command")
            if not cmd:
                return json.dumps({"ok": False, "error": "vm_exec requires 'command'"})
            res = self.execute_in_vm(target, cmd, timeout=float(args.get("timeout", 60.0)))
            return json.dumps(res.to_dict())

        if action == "vm_file":
            src = args.get("source_path")
            dst = args.get("dest_path")
            if not src or not dst:
                return json.dumps({"ok": False, "error": "vm_file requires 'source_path' and 'dest_path'"})
            dir_mode = vm_action or "upload"
            return json.dumps(self.transfer_file(target, src, dst, direction=dir_mode))

        if action == "cursor_position":
            pos = self._last_cursor_pos.get(target, (0, 0))
            return json.dumps({
                "ok": True, "action": "cursor_position",
                "x": pos[0], "y": pos[1], "coordinate": [pos[0], pos[1]],
                "output": f"X={pos[0]},Y={pos[1]}",
                "message": f"X={pos[0]},Y={pos[1]}",
            })

        if action in ("vm_capture", "capture"):
            png_b64, err, w, h = self.capture_screen(target)
            if err or not png_b64:
                return json.dumps({"ok": False, "error": err or "Failed to capture VM screen"})
            from tools.computer_use.backend import CaptureResult
            # Return CaptureResult so caller's _capture_response formats it properly
            return CaptureResult(
                mode="vision",
                width=w,
                height=h,
                png_b64=png_b64,
                elements=[],
                app=f"VM:{target}",
                window_title=f"Virtual Machine / VPS: {target} (Unattended)",
            )

        if action in (
            "vm_input", "type", "key", "click", "left_click", "double_click", "triple_click",
            "right_click", "middle_click", "drag", "left_click_drag", "scroll",
            "mouse_move", "mouse_down", "mouse_up", "left_mouse_down", "left_mouse_up",
        ):
            sub_action = action if action != "vm_input" else (vm_action or "click")
            coord = args.get("coordinate")
            x = coord[0] if coord and len(coord) > 0 else None
            y = coord[1] if coord and len(coord) > 1 else None
            from_c = args.get("from_coordinate")
            to_c = args.get("to_coordinate")
            from_xy = (from_c[0], from_c[1]) if from_c and len(from_c) >= 2 else None
            to_xy = (to_c[0], to_c[1]) if to_c and len(to_c) >= 2 else None
            return json.dumps(
                self.send_input(
                    target,
                    sub_action,
                    text=args.get("text"),
                    keys=args.get("keys"),
                    x=x,
                    y=y,
                    from_xy=from_xy,
                    to_xy=to_xy,
                    button=args.get("button", "left"),
                    direction=args.get("direction", "down"),
                    amount=args.get("amount", 3),
                )
            )

        return json.dumps({"ok": False, "error": f"Unknown VM action '{action}'"})


def check_vm_requirements() -> bool:
    """Expose the `vm` tool only when there is something to manage (no subprocesses)."""
    mgr = get_vm_manager()
    if mgr._load_inventory():
        return True
    if sys.platform == "win32":
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        if os.path.exists(os.path.join(system_root, "System32", "vmms.exe")):  # Hyper-V
            return True
    return any(mgr._providers[k].is_available() for k in ("wsl", "qemu", "vmware", "virtualbox"))


# Global process singleton
_global_vm_manager: Optional[VMManager] = None
_vm_manager_lock = threading.Lock()


def get_vm_manager() -> VMManager:
    """Return the global VMManager instance."""
    global _global_vm_manager
    with _vm_manager_lock:
        if _global_vm_manager is None:
            _global_vm_manager = VMManager()
        return _global_vm_manager
