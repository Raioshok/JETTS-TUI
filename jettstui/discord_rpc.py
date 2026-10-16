"""Discord Rich Presence (RPC) module for JettsTUI.

Connects to Discord's local IPC named pipe / Unix domain socket to display
rich activity on the user's Discord profile, showcasing JettsTUI, active AI
models, workspaces, tool executions, and clickable repository links.

Zero external dependencies: uses Python stdlib (asyncio, struct, json, socket).
Works across Windows, Linux (standard, Flatpak, Snap), and macOS.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import os
import platform
import struct
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# =============================================================================
# Protocol Constants
# =============================================================================

# Discord IPC Opcodes
OP_HANDSHAKE = 0
OP_FRAME = 1
OP_CLOSE = 2
OP_PING = 3
OP_PONG = 4

# Discord Rich Presence Default Application ID (Registered for JettsTUI)
# Users can also supply their own application ID via config or env var.
DEFAULT_CLIENT_ID = "1343714589234567890"

# Default Assets & Links
DEFAULT_LARGE_IMAGE = (
    "https://raw.githubusercontent.com/Raioshok/JETTS-TUI/main/apps/desktop/assets/icon.png"
)
DEFAULT_LARGE_TEXT = "JettsTUI — Autonomous AI Coding Agent"
DEFAULT_SMALL_IMAGE = (
    "https://raw.githubusercontent.com/Raioshok/JETTS-TUI/main/apps/desktop/public/apple-touch-icon.png"
)
DEFAULT_SMALL_TEXT = "⚡ Vibe Coding with AI"

DEFAULT_BUTTONS = [
    {
        "label": "⭐ Star on GitHub",
        "url": "https://github.com/Raioshok/JETTS-TUI",
    },
    {
        "label": "🚀 Try JettsTUI",
        "url": "https://github.com/Raioshok/JETTS-TUI",
    },
]

# Field length constraints enforced by Discord RPC API
MAX_DETAILS_LEN = 128
MAX_STATE_LEN = 128
MAX_TEXT_LEN = 128
MAX_BUTTONS = 2
MAX_BUTTON_LABEL_LEN = 32
MAX_BUTTON_URL_LEN = 512

# Minimum interval between presence updates to respect Discord RPC rate limits
UPDATE_DEBOUNCE_SECONDS = 1.5


# =============================================================================
# Data Structures
# =============================================================================


@dataclasses.dataclass
class ActivityButton:
    """A clickable button displayed on the Discord Rich Presence card."""

    label: str
    url: str

    def to_dict(self) -> dict[str, str]:
        return {
            "label": self.label[:MAX_BUTTON_LABEL_LEN],
            "url": self.url[:MAX_BUTTON_URL_LEN],
        }


@dataclasses.dataclass
class ActivityAssets:
    """Image assets and hover tooltips."""

    large_image: Optional[str] = DEFAULT_LARGE_IMAGE
    large_text: Optional[str] = DEFAULT_LARGE_TEXT
    small_image: Optional[str] = DEFAULT_SMALL_IMAGE
    small_text: Optional[str] = DEFAULT_SMALL_TEXT

    def to_dict(self) -> dict[str, str]:
        res: dict[str, str] = {}
        if self.large_image:
            res["large_image"] = str(self.large_image)
        if self.large_text:
            res["large_text"] = str(self.large_text)[:MAX_TEXT_LEN]
        if self.small_image:
            res["small_image"] = str(self.small_image)
        if self.small_text:
            res["small_text"] = str(self.small_text)[:MAX_TEXT_LEN]
        return res


@dataclasses.dataclass
class RichPresence:
    """Rich Presence state representation."""

    state: Optional[str] = None
    details: Optional[str] = None
    start_time: Optional[int] = None
    end_time: Optional[int] = None
    assets: Optional[ActivityAssets] = None
    buttons: Optional[List[Union[ActivityButton, dict[str, str]]]] = None
    instance: bool = True

    def to_payload_dict(self) -> dict[str, Any]:
        """Convert to sanitized dict pruned of None/empty values."""
        activity: dict[str, Any] = {}

        if self.state:
            activity["state"] = str(self.state)[:MAX_STATE_LEN]
        if self.details:
            activity["details"] = str(self.details)[:MAX_DETAILS_LEN]

        # Timestamps
        timestamps: dict[str, int] = {}
        if self.start_time is not None:
            timestamps["start"] = int(self.start_time)
        if self.end_time is not None:
            timestamps["end"] = int(self.end_time)
        if timestamps:
            activity["timestamps"] = timestamps

        # Assets
        if self.assets:
            assets_dict = self.assets.to_dict()
            if assets_dict:
                activity["assets"] = assets_dict

        # Buttons (Discord allows max 2)
        if self.buttons:
            sanitized_buttons: list[dict[str, str]] = []
            for btn in self.buttons[:MAX_BUTTONS]:
                if isinstance(btn, ActivityButton):
                    sanitized_buttons.append(btn.to_dict())
                elif isinstance(btn, dict) and "label" in btn and "url" in btn:
                    sanitized_buttons.append(
                        {
                            "label": str(btn["label"])[:MAX_BUTTON_LABEL_LEN],
                            "url": str(btn["url"])[:MAX_BUTTON_URL_LEN],
                        }
                    )
            if sanitized_buttons:
                activity["buttons"] = sanitized_buttons

        activity["instance"] = self.instance
        return activity


# =============================================================================
# Activity Presets
# =============================================================================

PRESETS: dict[str, dict[str, str]] = {
    "pairing": {
        "name": "Pairing",
        "description": "Pair-programming with AI in your terminal",
        "details": "⚡ Pairing with JettsTUI ({model})",
        "state": "📂 Workspace: {project}",
        "large_text": "JettsTUI — Autonomous AI Coding Agent",
        "small_text": "⚡ AI Pair Programmer",
    },
    "vibe_coding": {
        "name": "Vibe Coding",
        "description": "Flow state AI coding on your project",
        "details": "✨ Vibe Coding: {project}",
        "state": "🧠 {model} • Flow State",
        "large_text": "JettsTUI — SOTA AI Coding",
        "small_text": "🔥 100% Flow",
    },
    "autonomous": {
        "name": "Autonomous Agent",
        "description": "Multi-turn autonomous task execution",
        "details": "🤖 Autonomous Agent Running",
        "state": "⚡ {tools_count} tools active • {project}",
        "large_text": "JettsTUI — Autonomous Agent",
        "small_text": "🤖 Agentic Loop",
    },
    "fine_tuning": {
        "name": "Local LLM Fine-Tuning",
        "description": "Training and fine-tuning models locally",
        "details": "🔬 Local LLM Fine-Tuning ({model})",
        "state": "🎯 RTX 3060 CUDA • {project}",
        "large_text": "JettsTUI — MLOps & Fine-Tuning",
        "small_text": "🚀 GPU Training Active",
    },
    "idle": {
        "name": "Idle / Ready",
        "description": "Standing by for the next prompt",
        "details": "JettsTUI — Ready to Code",
        "state": "📂 {project}",
        "large_text": "JettsTUI — Personal AI Agent",
        "small_text": "💤 Standing by",
    },
}


def format_template(template: str, context: dict[str, Any]) -> str:
    """Format template string safely with fallbacks."""
    try:
        # Default empty substitutions
        safe_ctx = {
            "model": context.get("model") or "AI Agent",
            "provider": context.get("provider") or "Local",
            "project": context.get("project") or Path.cwd().name or "Workspace",
            "status": context.get("status") or "Active",
            "tools_count": context.get("tools_count", "12"),
            "session_id": context.get("session_id", ""),
        }
        return template.format(**safe_ctx)
    except Exception:
        return template


# =============================================================================
# Low-level IPC Transport
# =============================================================================


def get_ipc_pipe_candidates() -> list[str]:
    """Return ordered list of possible Discord IPC pipe paths for the OS."""
    system = platform.system().lower()
    candidates: list[str] = []

    if system == "windows":
        for i in range(10):
            candidates.append(rf"\\.\pipe\discord-ipc-{i}")
    elif system == "darwin":
        tmp = os.environ.get("TMPDIR") or tempfile.gettempdir()
        for i in range(10):
            candidates.append(os.path.join(tmp, f"discord-ipc-{i}"))
            candidates.append(f"/tmp/discord-ipc-{i}")
    else:  # Linux and other UNIX
        uid = os.getuid() if hasattr(os, "getuid") else 1000
        base_dirs = []

        xdg_runtime = os.environ.get("XDG_RUNTIME_DIR")
        if xdg_runtime:
            base_dirs.append(xdg_runtime)
            base_dirs.append(os.path.join(xdg_runtime, "app", "com.discordapp.Discord"))
            base_dirs.append(os.path.join(xdg_runtime, "snap.discord"))

        base_dirs.extend([
            f"/run/user/{uid}",
            f"/run/user/{uid}/app/com.discordapp.Discord",
            f"/run/user/{uid}/snap.discord",
            "/tmp",
        ])

        for bdir in base_dirs:
            if os.path.exists(bdir):
                for i in range(10):
                    candidates.append(os.path.join(bdir, f"discord-ipc-{i}"))

    return candidates


def find_active_ipc_pipe() -> Optional[str]:
    """Test candidate paths and return the first accessible Discord IPC pipe."""
    system = platform.system().lower()
    candidates = get_ipc_pipe_candidates()

    for path in candidates:
        if system == "windows":
            # On Windows, try opening pipe
            try:
                # Test with FileIO or os.stat
                with open(path, "r+b", buffering=0):
                    return path
            except (FileNotFoundError, OSError, PermissionError):
                continue
        else:
            # On UNIX, check if socket exists
            if os.path.exists(path):
                try:
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.settimeout(0.5)
                    s.connect(path)
                    s.close()
                    return path
                except (OSError, socket.error):
                    continue

    return None


class DiscordIPCClient:
    """Async client communicating directly with Discord's local IPC interface."""

    def __init__(
        self,
        client_id: str = DEFAULT_CLIENT_ID,
        pipe_path: Optional[str] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        self.client_id = str(client_id)
        self.pipe_path = pipe_path
        self._loop = loop
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.is_connected = False
        self.last_error = ""
        self._pid = os.getpid()

    async def connect(self) -> bool:
        """Connect to Discord IPC and perform initial handshake."""
        loop = self._loop or asyncio.get_running_loop()

        # Locate pipe if not explicitly set
        target_pipe = self.pipe_path
        if not target_pipe:
            candidates = get_ipc_pipe_candidates()
            for candidate in candidates:
                try:
                    if platform.system().lower() == "windows":
                        reader = asyncio.StreamReader(loop=loop)
                        protocol = asyncio.StreamReaderProtocol(reader, loop=loop)
                        transport, _ = await loop.create_pipe_connection(
                            lambda: protocol, candidate
                        )
                        self.writer = asyncio.StreamWriter(transport, protocol, reader, loop)
                        self.reader = reader
                    else:
                        if not os.path.exists(candidate):
                            continue
                        self.reader, self.writer = await asyncio.open_unix_connection(
                            candidate
                        )
                    target_pipe = candidate
                    break
                except (FileNotFoundError, ConnectionRefusedError, OSError):
                    continue

        if not self.reader or not self.writer or not target_pipe:
            return False

        self.pipe_path = target_pipe

        # Send Handshake (Opcode 0)
        handshake_payload = {"v": 1, "client_id": self.client_id}
        await self._send_packet(OP_HANDSHAKE, handshake_payload)

        # Read Handshake Response
        try:
            op, response = await self._read_packet(timeout=3.0)
        except Exception as exc:
            logger.debug("Failed to read Discord handshake response: %s", exc)
            await self.close()
            return False

        if "code" in response or response.get("evt") == "ERROR":
            msg = response.get("message") or (response.get("data") or {}).get("message") or "Handshake rejected"
            self.last_error = f"Discord error ({response.get('code')}): {msg}"
            logger.warning("Discord RPC Handshake rejected: %s", self.last_error)
            await self.close()
            return False

        self.is_connected = True
        logger.debug("Discord RPC connected successfully on %s", target_pipe)
        return True

    async def _send_packet(self, op: int, payload: dict[str, Any]) -> None:
        """Pack and send an IPC frame."""
        if not self.writer:
            raise ConnectionError("Discord IPC writer is not connected")

        payload_bytes = json.dumps(payload).encode("utf-8")
        header = struct.pack("<II", op, len(payload_bytes))
        self.writer.write(header + payload_bytes)
        drain = getattr(self.writer, "drain", None)
        if drain is not None:
            res = drain()
            if asyncio.iscoroutine(res):
                await res

    async def _read_packet(self, timeout: float = 3.0) -> Tuple[int, dict[str, Any]]:
        """Read and unpack an incoming IPC packet."""
        if not self.reader:
            raise ConnectionError("Discord IPC reader is not connected")

        preamble = await asyncio.wait_for(self.reader.readexactly(8), timeout=timeout)
        op, length = struct.unpack("<II", preamble)
        data = await asyncio.wait_for(self.reader.readexactly(length), timeout=timeout)
        payload = json.loads(data.decode("utf-8"))
        return op, payload

    async def set_activity(self, presence: RichPresence) -> bool:
        """Send SET_ACTIVITY command to Discord."""
        if not self.is_connected:
            return False

        payload = {
            "cmd": "SET_ACTIVITY",
            "args": {
                "pid": self._pid,
                "activity": presence.to_payload_dict(),
            },
            "nonce": str(uuid.uuid4()),
        }

        try:
            await self._send_packet(OP_FRAME, payload)
            # Read response
            op, resp = await self._read_packet(timeout=2.0)
            if op == OP_FRAME and resp.get("evt") == "ERROR":
                logger.debug("Discord set_activity error response: %s", resp.get("data"))
                return False
            return True
        except (asyncio.TimeoutError, ConnectionError, OSError) as exc:
            logger.debug("Discord set_activity failed: %s", exc)
            self.is_connected = False
            return False

    async def clear_activity(self) -> bool:
        """Clear active Rich Presence from Discord."""
        if not self.is_connected:
            return False

        payload = {
            "cmd": "SET_ACTIVITY",
            "args": {
                "pid": self._pid,
                "activity": None,
            },
            "nonce": str(uuid.uuid4()),
        }

        try:
            await self._send_packet(OP_FRAME, payload)
            await self._read_packet(timeout=1.0)
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """Close connection to Discord IPC."""
        self.is_connected = False
        if self.writer:
            try:
                # Send close opcode
                await self._send_packet(OP_CLOSE, {"v": 1, "client_id": self.client_id})
            except Exception:
                pass
            try:
                self.writer.close()
                if hasattr(self.writer, "wait_closed"):
                    await self.writer.wait_closed()
            except Exception:
                pass
        self.writer = None
        self.reader = None


# =============================================================================
# High-Level Background RPC Manager
# =============================================================================


class DiscordRPCManager:
    """Thread-safe background manager that synchronizes JettsTUI state with Discord."""

    def __init__(
        self,
        client_id: str = DEFAULT_CLIENT_ID,
        preset: str = "pairing",
        buttons: Optional[List[dict[str, str]]] = None,
        large_image: Optional[str] = DEFAULT_LARGE_IMAGE,
        large_text: Optional[str] = DEFAULT_LARGE_TEXT,
        small_image: Optional[str] = DEFAULT_SMALL_IMAGE,
        small_text: Optional[str] = DEFAULT_SMALL_TEXT,
        enabled: bool = True,
    ) -> None:
        self.client_id = client_id
        self.preset = preset
        self.buttons = buttons or DEFAULT_BUTTONS
        self.large_image = large_image
        self.large_text = large_text
        self.small_image = small_image
        self.small_text = small_text
        self.enabled = enabled

        self._start_time: int = int(time.time())
        self._current_model: str = ""
        self._current_project: str = Path.cwd().name
        self._current_tool: Optional[str] = None
        self._tools_count: int = 12
        self._status_text: str = "Active"

        self._custom_state: Optional[str] = None
        self._custom_details: Optional[str] = None

        self._worker_thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._client: Optional[DiscordIPCClient] = None
        self._stop_event = threading.Event()
        self._update_event = threading.Event()
        self._last_update_ts: float = 0.0
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start background worker thread."""
        if not self.enabled or (self._worker_thread and self._worker_thread.is_alive()):
            return

        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._run_event_loop,
            name="JettsTUI-DiscordRPC",
            daemon=True,
        )
        self._worker_thread.start()

    def stop(self) -> None:
        """Signal worker thread to stop and clean up."""
        self._stop_event.set()
        self._update_event.set()
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)
        self._worker_thread = None

    def _run_event_loop(self) -> None:
        """Worker thread body: maintains connection & dispatches activity updates."""
        # Windows requires ProactorEventLoop for create_pipe_connection
        if platform.system().lower() == "windows":
            self._loop = asyncio.ProactorEventLoop()
        else:
            self._loop = asyncio.new_event_loop()

        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._worker_main())
        except Exception as exc:
            logger.debug("DiscordRPC worker thread ended: %s", exc)
        finally:
            try:
                self._loop.close()
            except Exception:
                pass

    async def _worker_main(self) -> None:
        """Main async loop in background thread."""
        self._client = DiscordIPCClient(client_id=self.client_id, loop=self._loop)

        while not self._stop_event.is_set():
            if not self._client.is_connected:
                # Attempt to connect
                try:
                    connected = await self._client.connect()
                    if connected:
                        logger.debug("Connected to Discord RPC")
                        await self._push_current_activity()
                except Exception as exc:
                    logger.debug("Discord RPC connection attempt: %s", exc)

            if not self._client.is_connected:
                # Sleep before retrying connection
                for _ in range(10):
                    if self._stop_event.is_set():
                        break
                    await asyncio.sleep(0.5)
                continue

            # Connected: wait for update trigger or periodic heartbeat
            try:
                await asyncio.sleep(1.0)
                if self._update_event.is_set():
                    self._update_event.clear()
                    await self._push_current_activity()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("Discord RPC loop exception: %s", exc)
                self._client.is_connected = False

        # Clean shutdown
        if self._client and self._client.is_connected:
            try:
                await self._client.clear_activity()
                await self._client.close()
            except Exception:
                pass

    def build_current_presence(self) -> RichPresence:
        """Assemble current RichPresence instance from state and preset."""
        with self._lock:
            context = {
                "model": self._current_model or "AI Agent",
                "project": self._current_project or "Workspace",
                "tool": self._current_tool or "",
                "status": self._status_text,
                "tools_count": self._tools_count,
            }

            preset_info = PRESETS.get(self.preset, PRESETS["pairing"])

            if self._custom_details:
                details = format_template(self._custom_details, context)
            elif self._current_tool:
                details = f"⚡ Running: {self._current_tool}"
            else:
                details = format_template(preset_info["details"], context)

            if self._custom_state:
                state = format_template(self._custom_state, context)
            else:
                state = format_template(preset_info["state"], context)

            assets = ActivityAssets(
                large_image=self.large_image,
                large_text=preset_info.get("large_text", DEFAULT_LARGE_TEXT),
                small_image=self.small_image,
                small_text=(
                    f"Tool: {self._current_tool}"
                    if self._current_tool
                    else preset_info.get("small_text", DEFAULT_SMALL_TEXT)
                ),
            )

            buttons = [ActivityButton(b["label"], b["url"]) for b in self.buttons]

            return RichPresence(
                state=state,
                details=details,
                start_time=self._start_time,
                assets=assets,
                buttons=buttons,
            )

    async def _push_current_activity(self) -> None:
        """Push the current activity to Discord with debounce check."""
        now = time.time()
        if now - self._last_update_ts < UPDATE_DEBOUNCE_SECONDS:
            await asyncio.sleep(UPDATE_DEBOUNCE_SECONDS - (now - self._last_update_ts))

        presence = self.build_current_presence()
        if self._client and self._client.is_connected:
            success = await self._client.set_activity(presence)
            if success:
                self._last_update_ts = time.time()

    def notify_update(self) -> None:
        """Notify the background thread to push updated activity."""
        self._update_event.set()

    # Lifecycle hooks
    def on_session_start(self, model: str = "", project: Optional[str] = None) -> None:
        """Hook called when a conversation session begins."""
        with self._lock:
            if model:
                self._current_model = model
            if project:
                self._current_project = project
            self._start_time = int(time.time())
            self._current_tool = None
            self._status_text = "Active"
        self.notify_update()

    def on_tool_start(self, tool_name: str) -> None:
        """Hook called when the agent executes a tool."""
        with self._lock:
            self._current_tool = tool_name
            self._status_text = f"Using {tool_name}"
        self.notify_update()

    def on_tool_end(self, tool_name: str) -> None:
        """Hook called when a tool completes execution."""
        with self._lock:
            if self._current_tool == tool_name:
                self._current_tool = None
            self._status_text = "Thinking..."
        self.notify_update()

    def on_turn_end(self) -> None:
        """Hook called when agent turn finishes."""
        with self._lock:
            self._current_tool = None
            self._status_text = "Ready"
        self.notify_update()

    def set_preset(self, preset_name: str) -> bool:
        """Switch to a predefined activity preset."""
        if preset_name not in PRESETS:
            return False
        with self._lock:
            self.preset = preset_name
            self._custom_state = None
            self._custom_details = None
        self.notify_update()
        return True

    def set_custom(self, state: Optional[str] = None, details: Optional[str] = None) -> None:
        """Set explicit custom status text."""
        with self._lock:
            if state is not None:
                self._custom_state = state
            if details is not None:
                self._custom_details = details
        self.notify_update()

    @property
    def is_connected(self) -> bool:
        return bool(self._client and self._client.is_connected)


# =============================================================================
# Global Manager Singleton
# =============================================================================

_RPC_MANAGER: Optional[DiscordRPCManager] = None
_RPC_LOCK = threading.Lock()


def get_rpc_manager() -> Optional[DiscordRPCManager]:
    """Retrieve active Discord RPC manager singleton."""
    return _RPC_MANAGER


def init_rpc_manager(config: Optional[dict[str, Any]] = None) -> DiscordRPCManager:
    """Initialize or update the global Discord RPC manager from configuration."""
    global _RPC_MANAGER
    cfg = (config or {}).get("discord_rpc", {})

    client_id = (
        os.environ.get("DISCORD_RPC_CLIENT_ID")
        or cfg.get("client_id")
        or DEFAULT_CLIENT_ID
    )

    with _RPC_LOCK:
        if _RPC_MANAGER is None:
            _RPC_MANAGER = DiscordRPCManager(
                client_id=client_id,
                preset=cfg.get("preset", "pairing"),
                buttons=cfg.get("buttons") or DEFAULT_BUTTONS,
                large_image=cfg.get("large_image") or DEFAULT_LARGE_IMAGE,
                large_text=cfg.get("large_text") or DEFAULT_LARGE_TEXT,
                small_image=cfg.get("small_image") or DEFAULT_SMALL_IMAGE,
                small_text=cfg.get("small_text") or DEFAULT_SMALL_TEXT,
                enabled=cfg.get("enabled", False),
            )
        else:
            _RPC_MANAGER.client_id = client_id
            _RPC_MANAGER.preset = cfg.get("preset", _RPC_MANAGER.preset)
            _RPC_MANAGER.enabled = cfg.get("enabled", _RPC_MANAGER.enabled)
            if "buttons" in cfg:
                _RPC_MANAGER.buttons = cfg["buttons"]

        if _RPC_MANAGER.enabled:
            _RPC_MANAGER.start()

    return _RPC_MANAGER


def stop_rpc_manager() -> None:
    """Stop and release global Discord RPC manager."""
    global _RPC_MANAGER
    with _RPC_LOCK:
        if _RPC_MANAGER is not None:
            _RPC_MANAGER.stop()
            _RPC_MANAGER = None


# =============================================================================
# Terminal Profile Card Visual Renderer
# =============================================================================


def render_discord_card(
    presence: RichPresence,
    client_name: str = "JettsTUI",
    is_connected: bool = True,
    pipe_path: Optional[str] = None,
) -> Any:
    """Render a realistic, beautiful terminal simulation of a Discord Profile card.

    Uses Rich if available for authentic Discord theme styling.
    """
    try:
        from rich.box import ROUNDED
        from rich.console import Console, Group
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text

        # Status indicator
        status_dot = "🟢" if is_connected else "⚪"
        status_text = (
            Text(" CONNECTED TO DISCORD", style="bold green")
            if is_connected
            else Text(" DISCORD NOT DETECTED", style="bold yellow")
        )

        header = Text.assemble(
            (f"{status_dot} ", ""),
            status_text,
            (f"  •  Pipe: {pipe_path or 'auto-search'}", "dim italic"),
        )

        # Discord User Profile Card Simulation
        profile_table = Table.grid(padding=(0, 2))
        profile_table.add_column(style="bold white", width=14)
        profile_table.add_column()

        # Application Header
        profile_table.add_row(
            Text("PLAYING A GAME", style="bold #949BA4"),
            Text(""),
        )
        profile_table.add_row(
            Text(client_name, style="bold #F2F3F5"),
            Text(""),
        )

        # Details line
        if presence.details:
            profile_table.add_row(
                Text("Details", style="dim #B5BAC1"),
                Text(presence.details, style="bold #DBDEE1"),
            )

        # State line
        if presence.state:
            profile_table.add_row(
                Text("State", style="dim #B5BAC1"),
                Text(presence.state, style="#DBDEE1"),
            )

        # Elapsed timestamp
        if presence.start_time:
            elapsed_sec = max(0, int(time.time() - presence.start_time))
            mins, secs = divmod(elapsed_sec, 60)
            hours, mins = divmod(mins, 60)
            elapsed_str = f"{hours:02d}:{mins:02d}:{secs:02d} elapsed"
            profile_table.add_row(
                Text("Time", style="dim #B5BAC1"),
                Text(f"⏱️ {elapsed_str}", style="#57F287"),
            )

        # Assets
        if presence.assets:
            asset_info = []
            if presence.assets.large_text:
                asset_info.append(f"Icon: {presence.assets.large_text}")
            if presence.assets.small_text:
                asset_info.append(f"Badge: {presence.assets.small_text}")
            if asset_info:
                profile_table.add_row(
                    Text("Assets", style="dim #B5BAC1"),
                    Text(" • ".join(asset_info), style="dim"),
                )

        # Buttons table
        button_elements: list[Text] = []
        if presence.buttons:
            for btn in presence.buttons:
                label = btn.label if isinstance(btn, ActivityButton) else btn.get("label", "")
                url = btn.url if isinstance(btn, ActivityButton) else btn.get("url", "")
                button_elements.append(
                    Text.assemble(
                        ("  [ ", "#5865F2"),
                        (f"{label}", "bold white"),
                        (" ]  ", "#5865F2"),
                        (f"({url})", "dim underline"),
                    )
                )

        content_items = [profile_table]
        if button_elements:
            content_items.append(Text("\nInteractive Profile Buttons:", style="bold #949BA4"))
            for b in button_elements:
                content_items.append(b)

        return Panel(
            Group(*content_items),
            title=f"[bold #5865F2]🎮 Discord Rich Presence — {client_name}[/]",
            subtitle=header,
            border_style="#5865F2",
            box=ROUNDED,
            padding=(1, 2),
        )

    except ImportError:
        # Fallback if Rich is unavailable
        lines = [
            f"=== Discord Rich Presence: {client_name} ===",
            f"Status: {'CONNECTED' if is_connected else 'DISCONNECTED'}",
            f"Details: {presence.details}",
            f"State: {presence.state}",
        ]
        if presence.buttons:
            for b in presence.buttons:
                l = b.label if isinstance(b, ActivityButton) else b.get("label")
                u = b.url if isinstance(b, ActivityButton) else b.get("url")
                lines.append(f"Button: [{l}] -> {u}")
        return "\n".join(lines)


# =============================================================================
# Standalone CLI Entry Point
# =============================================================================


def main() -> None:
    """CLI runner: `python -m jettstui.discord_rpc`."""
    import argparse

    parser = argparse.ArgumentParser(
        description="JettsTUI Discord Rich Presence (RPC) manager & diagnostic tool."
    )
    parser.add_argument("--status", action="store_true", help="Display current Discord status and card")
    parser.add_argument("--test", action="store_true", help="Send a live test presence to Discord")
    parser.add_argument("--preset", choices=list(PRESETS.keys()), default="pairing", help="Select preset")
    parser.add_argument("--state", type=str, help="Custom state string")
    parser.add_argument("--details", type=str, help="Custom details string")
    parser.add_argument("--client-id", type=str, default=DEFAULT_CLIENT_ID, help="Discord Application ID")
    parser.add_argument("--daemon", action="store_true", help="Run presence daemon in foreground")

    args = parser.parse_args()

    try:
        from rich.console import Console

        console = Console()
    except ImportError:
        console = None

    mgr = DiscordRPCManager(
        client_id=args.client_id,
        preset=args.preset,
        enabled=True,
    )
    if args.state or args.details:
        mgr.set_custom(state=args.state, details=args.details)

    pipe = find_active_ipc_pipe()
    presence = mgr.build_current_presence()
    card = render_discord_card(
        presence,
        client_name="JettsTUI",
        is_connected=bool(pipe),
        pipe_path=pipe,
    )

    if console:
        console.print(card)
    else:
        print(card)

    if args.test or args.daemon:
        print("\nConnecting to Discord IPC...")

        async def run_test():
            client = DiscordIPCClient(client_id=args.client_id)
            ok = await client.connect()
            if not ok:
                print("❌ Could not connect to Discord! Is the Discord desktop app running?")
                return
            print(f"✅ Connected to Discord pipe: {client.pipe_path}")
            print("🚀 Pushing Rich Presence activity...")
            await client.set_activity(presence)
            print("✨ Presence active! Check your Discord profile.")
            if args.daemon:
                print("Running in daemon mode. Press Ctrl+C to exit.")
                while True:
                    await asyncio.sleep(1)
            else:
                print("Keeping alive for 15 seconds so you can see it...")
                await asyncio.sleep(15)
            await client.clear_activity()
            await client.close()
            print("Cleared and disconnected.")

        try:
            if platform.system().lower() == "windows":
                loop = asyncio.ProactorEventLoop()
            else:
                loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(run_test())
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
