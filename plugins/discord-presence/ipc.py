"""Minimal, dependency-free Discord RPC client over the local IPC socket.

Discord exposes a framed JSON protocol on a named pipe (Windows) or a Unix
domain socket (Linux/macOS). Every frame is a little-endian ``<II`` header
(opcode, payload length) followed by a UTF-8 JSON body.

The client is deliberately synchronous: one worker thread owns it, writes a
command, then reads frames until the reply with the matching ``nonce``
arrives (answering PINGs and surfacing CLOSE frames along the way). Windows
pipe handles opened without overlapped I/O serialize reads and writes, so a
background reader thread would deadlock every write — polling the pipe with
``PeekNamedPipe`` gives us read timeouts without that hazard.
"""

from __future__ import annotations

import json
import os
import socket
import struct
import sys
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Protocol

OP_HANDSHAKE = 0
OP_FRAME = 1
OP_CLOSE = 2
OP_PING = 3
OP_PONG = 4

_HEADER = struct.Struct("<II")
_MAX_FRAME_BYTES = 1 << 20

# Discord close codes worth translating for the user.
CLOSE_INVALID_CLIENT_ID = 4000


class DiscordIPCError(Exception):
    """Discord rejected a request or closed the connection."""

    def __init__(self, message: str, code: Optional[int] = None) -> None:
        super().__init__(message)
        self.code = code


class DiscordNotRunning(DiscordIPCError):
    """No Discord client is listening on any known IPC path."""


class Transport(Protocol):
    def send(self, data: bytes) -> None: ...

    def recv_exact(self, size: int, deadline: float) -> bytes: ...

    def close(self) -> None: ...


def ipc_candidates(platform: str = sys.platform, env: Optional[Dict[str, str]] = None) -> List[str]:
    """Return every IPC path a Discord client may be listening on, in order."""
    env = os.environ if env is None else env
    if platform == "win32":
        return [rf"\\?\pipe\discord-ipc-{i}" for i in range(10)]

    bases: List[str] = []
    for key in ("XDG_RUNTIME_DIR", "TMPDIR", "TMP", "TEMP"):
        value = (env.get(key) or "").strip()
        if value:
            bases.append(value)
    getuid = getattr(os, "getuid", None)
    if getuid is not None:
        bases.append(f"/run/user/{getuid()}")
    bases.append("/tmp")

    # Sandboxed installs (Flatpak, Snap, Vesktop) put the socket in a subdir.
    subdirs = ("", "app/com.discordapp.Discord", "snap.discord", ".flatpak/dev.vencord.Vesktop/xdg-run")
    seen: set = set()
    paths: List[str] = []
    for base in bases:
        for sub in subdirs:
            for i in range(10):
                path = os.path.join(base, sub, f"discord-ipc-{i}") if sub else os.path.join(base, f"discord-ipc-{i}")
                if path not in seen:
                    seen.add(path)
                    paths.append(path)
    return paths


class _PipeTransport:
    """Windows named pipe with deadline-bounded reads via ``PeekNamedPipe``."""

    def __init__(self, path: str) -> None:
        import ctypes
        import msvcrt
        from ctypes import wintypes

        self._file = open(path, "r+b", buffering=0)  # noqa: SIM115 - closed in close()
        self._handle = msvcrt.get_osfhandle(self._file.fileno())
        self._ctypes = ctypes
        self._peek = ctypes.windll.kernel32.PeekNamedPipe
        self._peek.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_void_p,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.c_void_p,
        ]
        self._peek.restype = wintypes.BOOL
        self._dword = wintypes.DWORD

    def _available(self) -> int:
        total = self._dword(0)
        if not self._peek(self._handle, None, 0, None, self._ctypes.byref(total), None):
            raise ConnectionError("Discord IPC pipe closed")
        return int(total.value)

    def send(self, data: bytes) -> None:
        view = memoryview(data)
        while view:
            written = self._file.write(view)
            if not written:
                raise ConnectionError("Discord IPC pipe closed")
            view = view[written:]

    def recv_exact(self, size: int, deadline: float) -> bytes:
        buf = bytearray()
        while len(buf) < size:
            available = self._available()
            if available <= 0:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Timed out waiting for Discord")
                time.sleep(0.02)
                continue
            chunk = self._file.read(min(size - len(buf), available))
            if not chunk:
                raise ConnectionError("Discord IPC pipe closed")
            buf.extend(chunk)
        return bytes(buf)

    def close(self) -> None:
        try:
            self._file.close()
        except OSError:
            pass


class _SocketTransport:
    """Unix domain socket transport."""

    def __init__(self, path: str) -> None:
        family = getattr(socket, "AF_UNIX", None)
        if family is None:
            raise OSError("Unix sockets are unavailable on this platform")
        self._sock = socket.socket(family, socket.SOCK_STREAM)
        self._sock.settimeout(2.0)
        try:
            self._sock.connect(path)
        except OSError:
            self._sock.close()
            raise

    def send(self, data: bytes) -> None:
        self._sock.settimeout(5.0)
        self._sock.sendall(data)

    def recv_exact(self, size: int, deadline: float) -> bytes:
        buf = bytearray()
        while len(buf) < size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Timed out waiting for Discord")
            self._sock.settimeout(remaining)
            try:
                chunk = self._sock.recv(size - len(buf))
            except socket.timeout as exc:
                raise TimeoutError("Timed out waiting for Discord") from exc
            if not chunk:
                raise ConnectionError("Discord IPC socket closed")
            buf.extend(chunk)
        return bytes(buf)

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass


def default_transport(path: str) -> Transport:
    if sys.platform == "win32":
        return _PipeTransport(path)
    return _SocketTransport(path)


def encode_frame(opcode: int, payload: Dict[str, Any]) -> bytes:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return _HEADER.pack(opcode, len(body)) + body


class DiscordIPC:
    """One authenticated connection to the local Discord client."""

    def __init__(
        self,
        client_id: str,
        *,
        candidates: Optional[List[str]] = None,
        transport_factory: Callable[[str], Transport] = default_transport,
    ) -> None:
        self.client_id = str(client_id)
        self._candidates = candidates
        self._transport_factory = transport_factory
        self._transport: Optional[Transport] = None
        self.path: Optional[str] = None
        self.user: Dict[str, Any] = {}

    @property
    def connected(self) -> bool:
        return self._transport is not None

    def connect(self, timeout: float = 5.0) -> Dict[str, Any]:
        """Open the first live IPC path and complete the handshake.

        Returns the Discord user from the READY dispatch.
        """
        candidates = self._candidates if self._candidates is not None else ipc_candidates()
        last_error: Optional[Exception] = None
        for path in candidates:
            try:
                transport = self._transport_factory(path)
            except (OSError, ValueError):
                continue
            self._transport = transport
            self.path = path
            try:
                self._send(OP_HANDSHAKE, {"v": 1, "client_id": self.client_id})
                opcode, data = self._read_frame(time.monotonic() + timeout)
            except (OSError, TimeoutError, ValueError) as exc:
                # A stale socket file or a client that never answered — try
                # the next path rather than failing the whole connect.
                self._drop()
                last_error = exc
                continue
            if opcode == OP_CLOSE:
                self._drop()
                raise _close_error(data)
            if data.get("evt") == "READY":
                self.user = dict((data.get("data") or {}).get("user") or {})
                return self.user
            self._drop()
            raise DiscordIPCError(f"Unexpected handshake reply: {data.get('evt') or opcode}")
        detail = f" ({last_error})" if last_error else ""
        raise DiscordNotRunning(f"Discord is not running or IPC is unavailable{detail}")

    def request(self, command: str, args: Dict[str, Any], timeout: float = 5.0) -> Dict[str, Any]:
        """Send one command and wait for the reply carrying its nonce."""
        if self._transport is None:
            raise DiscordIPCError("Not connected to Discord")
        nonce = uuid.uuid4().hex
        try:
            self._send(OP_FRAME, {"cmd": command, "args": args, "nonce": nonce})
            deadline = time.monotonic() + timeout
            while True:
                opcode, data = self._read_frame(deadline)
                if opcode == OP_PING:
                    self._send(OP_PONG, data)
                    continue
                if opcode == OP_CLOSE:
                    self._drop()
                    raise _close_error(data)
                if opcode != OP_FRAME or data.get("nonce") != nonce:
                    continue  # unrelated dispatch
                if data.get("evt") == "ERROR":
                    err = data.get("data") or {}
                    raise DiscordIPCError(str(err.get("message") or "Discord rejected the request"), err.get("code"))
                return data
        except (OSError, TimeoutError, ValueError) as exc:
            self._drop()
            raise DiscordIPCError(f"Lost connection to Discord: {exc}") from exc

    def set_activity(self, activity: Optional[Dict[str, Any]], pid: Optional[int] = None) -> Dict[str, Any]:
        """Set (or, with ``None``, clear) this process's activity."""
        return self.request("SET_ACTIVITY", {"pid": pid or os.getpid(), "activity": activity})

    def close(self) -> None:
        if self._transport is None:
            return
        try:
            self._send(OP_CLOSE, {})
        except OSError:
            pass
        self._drop()

    def _drop(self) -> None:
        transport, self._transport = self._transport, None
        if transport is not None:
            transport.close()

    def _send(self, opcode: int, payload: Dict[str, Any]) -> None:
        assert self._transport is not None
        self._transport.send(encode_frame(opcode, payload))

    def _read_frame(self, deadline: float) -> tuple:
        assert self._transport is not None
        opcode, length = _HEADER.unpack(self._transport.recv_exact(_HEADER.size, deadline))
        if length > _MAX_FRAME_BYTES:
            raise ValueError(f"Discord frame too large ({length} bytes)")
        body = self._transport.recv_exact(length, deadline) if length else b"{}"
        data = json.loads(body.decode("utf-8") or "{}")
        return opcode, data if isinstance(data, dict) else {}


def _close_error(data: Dict[str, Any]) -> DiscordIPCError:
    code = data.get("code")
    message = str(data.get("message") or "Discord closed the connection")
    if code == CLOSE_INVALID_CLIENT_ID:
        message = "Discord rejected the Application ID (check discord_rpc.client_id)"
    return DiscordIPCError(message, code)
