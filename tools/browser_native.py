"""Native Chrome DevTools Protocol driver for the ``browser_*`` tools.

A self-contained, pure-Python replacement for the ``agent-browser`` Node CLI.
It launches any installed Chromium-family browser (Chrome, Edge, Chromium,
Brave, or a Playwright-downloaded build) with ``--remote-debugging-port=0``,
or attaches to an existing CDP endpoint (``browser.cdp_url`` / cloud
providers), and drives it over one persistent WebSocket.

The public entry point :func:`run_command` mirrors the ``agent-browser
--json`` result contract (``{"success": bool, "data": {...}}`` /
``{"success": False, "error": str}``) so ``tools/browser_tool.py`` can swap
drivers without touching any of its higher-level logic (SSRF guards,
snapshot truncation, vision, console redaction).

Snapshots are built from the browser's own accessibility tree
(``Accessibility.getFullAXTree``) in the same ``- role "name" [ref=eN]``
format the tools have always returned; refs resolve to ``backendDOMNodeId``s
so clicks and typing hit the exact element the model saw.
"""

from __future__ import annotations

import atexit
import base64
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Browser executable discovery
# =============================================================================

def _windows_candidates() -> List[str]:
    roots = [
        os.environ.get("PROGRAMFILES", r"C:\Program Files"),
        os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
        os.environ.get("LOCALAPPDATA", os.path.join(os.path.expanduser("~"), "AppData", "Local")),
    ]
    rel = (
        r"Google\Chrome\Application\chrome.exe",
        r"Chromium\Application\chrome.exe",
        r"Microsoft\Edge\Application\msedge.exe",
        r"BraveSoftware\Brave-Browser\Application\brave.exe",
    )
    return [os.path.join(root, r) for r in rel for root in roots if root]


_MAC_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
)

_PATH_NAMES = (
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
    "chrome", "microsoft-edge", "microsoft-edge-stable", "brave-browser", "msedge",
)


def _playwright_candidates() -> List[str]:
    """Chromium builds downloaded by Playwright / older agent-browser installs."""
    roots: List[str] = []
    env_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if env_path and env_path != "0":
        roots.append(env_path)
    home = os.path.expanduser("~")
    roots.append(os.path.join(home, ".cache", "ms-playwright"))
    if sys.platform == "darwin":
        roots.append(os.path.join(home, "Library", "Caches", "ms-playwright"))
    if sys.platform == "win32":
        roots.append(os.path.join(os.environ.get("LOCALAPPDATA", os.path.join(home, "AppData", "Local")), "ms-playwright"))

    found: List[str] = []
    shells: List[str] = []  # headless-only builds rank after full Chromium
    for root in roots:
        try:
            entries = sorted(os.listdir(root), reverse=True)  # newest build first
        except OSError:
            continue
        for entry in entries:
            base = os.path.join(root, entry)
            if entry.startswith("chromium-"):
                found += [
                    os.path.join(base, "chrome-win", "chrome.exe"),
                    os.path.join(base, "chrome-win64", "chrome.exe"),
                    os.path.join(base, "chrome-linux", "chrome"),
                    os.path.join(base, "chrome-linux64", "chrome"),
                    os.path.join(base, "chrome-mac", "Chromium.app", "Contents", "MacOS", "Chromium"),
                ]
            elif entry.startswith("chromium_headless_shell-"):
                for sub in ("chrome-win", "chrome-linux", "chrome-mac", "chrome-headless-shell-win64",
                            "chrome-headless-shell-linux64", "chrome-headless-shell-mac-arm64",
                            "chrome-headless-shell-mac-x64"):
                    shells += [
                        os.path.join(base, sub, "headless_shell.exe"),
                        os.path.join(base, sub, "headless_shell"),
                        os.path.join(base, sub, "chrome-headless-shell.exe"),
                        os.path.join(base, sub, "chrome-headless-shell"),
                    ]
    return found + shells


def _configured_executable() -> str:
    try:
        from jettstui.config import cfg_get

        value = cfg_get("browser.executable_path", "") or ""
    except Exception:
        value = ""
    # AGENT_BROWSER_EXECUTABLE_PATH is honoured for back-compat with existing
    # setups that pointed the old CLI at a specific Chrome.
    return str(value).strip() or os.environ.get("AGENT_BROWSER_EXECUTABLE_PATH", "").strip()


_executable_cache: Optional[Tuple[str, Optional[str]]] = None


def find_browser_executable() -> Optional[str]:
    """Return the path of a launchable Chromium-family browser, or ``None``.

    Order: ``browser.executable_path`` config → well-known install locations
    → ``PATH`` → Playwright's browser cache. Cached per configured value so
    tool-schema assembly stays cheap.
    """
    global _executable_cache
    configured = _configured_executable()
    if _executable_cache is not None and _executable_cache[0] == configured:
        return _executable_cache[1]

    result: Optional[str] = None
    if configured:
        result = configured if os.path.isfile(configured) else shutil.which(configured)
    if result is None:
        candidates: List[str] = []
        if sys.platform == "win32":
            candidates += _windows_candidates()
        elif sys.platform == "darwin":
            candidates += list(_MAC_CANDIDATES)
        for c in candidates:
            if os.path.isfile(c):
                result = c
                break
    if result is None:
        for name in _PATH_NAMES:
            hit = shutil.which(name)
            if hit:
                result = hit
                break
    if result is None:
        for c in _playwright_candidates():
            if os.path.isfile(c):
                result = c
                break

    _executable_cache = (configured, result)
    return result


def _reset_executable_cache() -> None:
    global _executable_cache
    _executable_cache = None


def install_hint() -> str:
    if sys.platform == "win32":
        return "Install Google Chrome or Microsoft Edge, or set browser.executable_path in config.yaml."
    if sys.platform == "darwin":
        return "Install Google Chrome (or Chromium/Edge/Brave), or set browser.executable_path in config.yaml."
    return (
        "Install Chromium (e.g. `sudo apt install chromium` or `sudo dnf install chromium`) "
        "or Google Chrome, or set browser.executable_path in config.yaml."
    )


# =============================================================================
# CDP connection
# =============================================================================

class CDPError(RuntimeError):
    """A CDP command returned an error, timed out, or the socket died."""


class DialogBlocked(CDPError):
    """The page opened a JavaScript dialog while a command was waiting."""


class CDPConnection:
    """Minimal thread-safe CDP client over a synchronous WebSocket.

    A daemon reader thread routes command responses to waiting callers and
    hands events to ``on_event``. ``send`` may be called from any thread.
    """

    def __init__(self, ws_url: str, on_event: Callable[[Dict[str, Any]], None], *, local: bool):
        from websockets.sync.client import connect

        kwargs: Dict[str, Any] = {"max_size": None, "open_timeout": 15, "close_timeout": 2}
        if local:
            # websockets >= 15 honours HTTP(S)_PROXY for ws:// by default; a
            # loopback DevTools socket must never be routed through a proxy.
            kwargs["proxy"] = None
        try:
            self._ws = connect(ws_url, **kwargs)
        except TypeError:
            kwargs.pop("proxy", None)
            self._ws = connect(ws_url, **kwargs)
        self._on_event = on_event
        self._next_id = 0
        self._id_lock = threading.Lock()
        self._pending: Dict[int, Dict[str, Any]] = {}
        self._pending_lock = threading.Lock()
        self.closed = False
        self._reader = threading.Thread(target=self._read_loop, name="cdp-native-reader", daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        try:
            while True:
                raw = self._ws.recv()
                try:
                    msg = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                msg_id = msg.get("id")
                if msg_id is not None:
                    with self._pending_lock:
                        slot = self._pending.get(msg_id)
                    if slot is not None:
                        slot["msg"] = msg
                        slot["event"].set()
                elif "method" in msg:
                    try:
                        self._on_event(msg)
                    except Exception as exc:  # pragma: no cover — defensive
                        logger.debug("native CDP event handler raised: %s", exc)
        except Exception as exc:
            logger.debug("native CDP reader stopped: %s", exc)
        finally:
            self.closed = True
            with self._pending_lock:
                for slot in self._pending.values():
                    slot["event"].set()

    def send(self, method: str, params: Optional[Dict[str, Any]] = None, *,
             session_id: Optional[str] = None, timeout: float = 30.0,
             abort: Optional[Callable[[], bool]] = None) -> Dict[str, Any]:
        """Send a command and wait for its result.

        ``abort`` is polled while waiting; when it returns True the wait ends
        with :class:`DialogBlocked` (the renderer is stuck in a dialog and
        will not answer until someone responds to it).
        """
        if self.closed:
            raise CDPError("browser connection is closed")
        with self._id_lock:
            self._next_id += 1
            msg_id = self._next_id
        payload: Dict[str, Any] = {"id": msg_id, "method": method, "params": params or {}}
        if session_id:
            payload["sessionId"] = session_id
        slot: Dict[str, Any] = {"event": threading.Event(), "msg": None}
        with self._pending_lock:
            self._pending[msg_id] = slot
        try:
            self._ws.send(json.dumps(payload))
            deadline = time.monotonic() + timeout
            while not slot["event"].wait(0.1 if abort else timeout):
                if abort is not None and abort():
                    raise DialogBlocked(f"{method} interrupted by a JavaScript dialog")
                if time.monotonic() >= deadline:
                    raise CDPError(f"{method} timed out after {timeout:.0f}s")
        except CDPError:
            raise
        except Exception as exc:
            raise CDPError(f"{method} failed: {exc}") from exc
        finally:
            with self._pending_lock:
                self._pending.pop(msg_id, None)
        msg = slot["msg"]
        if msg is None:
            raise CDPError("browser connection closed")
        if "error" in msg:
            err = msg["error"]
            raise CDPError(str(err.get("message") or err) + (f" ({err['data']})" if err.get("data") else ""))
        return msg.get("result", {})

    def close(self) -> None:
        self.closed = True
        try:
            self._ws.close()
        except Exception:
            pass


# =============================================================================
# Process launch + orphan reaping
# =============================================================================

def _profiles_root() -> Path:
    return Path(tempfile.gettempdir()) / "jettstui-browser"


def _pid_alive(pid: int) -> bool:
    try:
        import psutil

        return psutil.pid_exists(pid) and psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except Exception:
        return False


def _kill_tree(pid: int) -> None:
    try:
        import psutil

        proc = psutil.Process(pid)
        children = proc.children(recursive=True)
        for p in [proc, *children]:
            try:
                p.kill()
            except Exception:
                pass
        psutil.wait_procs([proc, *children], timeout=3)
    except Exception:
        pass


_reaped_once = False


def reap_orphaned_profiles() -> None:
    """Kill browsers + delete profiles left behind by dead jettstui processes.

    Each launched browser gets ``<tmp>/jettstui-browser/<session>/owner.json``
    naming the owning jettstui PID and the browser PID. A profile whose owner
    is gone is reaped; the browser PID is only killed when its command line
    still references that profile directory (PID-reuse safety).
    """
    root = _profiles_root()
    if not root.is_dir():
        return
    for entry in root.iterdir():
        owner_file = entry / "owner.json"
        try:
            info = json.loads(owner_file.read_text(encoding="utf-8"))
        except Exception:
            # Unreadable / half-written: only reap stale ones.
            try:
                if time.time() - entry.stat().st_mtime < 3600:
                    continue
            except OSError:
                continue
            info = {}
        owner = int(info.get("owner_pid") or 0)
        if owner and _pid_alive(owner):
            continue
        browser_pid = int(info.get("browser_pid") or 0)
        if browser_pid and _pid_alive(browser_pid):
            try:
                import psutil

                cmdline = " ".join(psutil.Process(browser_pid).cmdline())
                if str(entry) in cmdline:
                    _kill_tree(browser_pid)
            except Exception:
                pass
        shutil.rmtree(entry, ignore_errors=True)


def _launch_args(executable: str, profile_dir: Path, *, headed: bool, no_sandbox: bool) -> List[str]:
    args = [
        executable,
        "--remote-debugging-port=0",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-sync",
        "--disable-default-apps",
        "--disable-component-update",
        "--disable-features=Translate,MediaRouter,OptimizationHints",
        "--disable-blink-features=AutomationControlled",
        "--password-store=basic",
        "--use-mock-keychain",
        "--mute-audio",
        "--window-size=1280,900",
    ]
    if not headed:
        args.append("--headless=new")
    if no_sandbox:
        args += ["--no-sandbox", "--disable-dev-shm-usage"]
    args.append("about:blank")
    return args


def launch_browser(*, session_name: str, headed: bool, no_sandbox: bool,
                   timeout: float = 20.0) -> Tuple[subprocess.Popen, str, Path]:
    """Start a browser and return ``(process, browser_ws_url, profile_dir)``."""
    global _reaped_once
    if not _reaped_once:
        _reaped_once = True
        try:
            reap_orphaned_profiles()
        except Exception as exc:
            logger.debug("native browser orphan reap failed: %s", exc)

    executable = find_browser_executable()
    if not executable:
        raise CDPError("No Chrome/Chromium/Edge browser found. " + install_hint())

    # Unique per launch: a relaunch must never share a profile with a
    # previous instance that is still shutting down (Chrome exits with 21).
    profile_dir = _profiles_root() / f"{session_name}-{uuid.uuid4().hex[:6]}"
    profile_dir.mkdir(parents=True, exist_ok=True)
    port_file = profile_dir / "DevToolsActivePort"
    try:
        port_file.unlink()
    except OSError:
        pass

    popen_kwargs: Dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        from jettstui._subprocess_compat import windows_hide_flags

        popen_kwargs["creationflags"] = windows_hide_flags()
        popen_kwargs["close_fds"] = True
    else:
        popen_kwargs["start_new_session"] = True

    proc = subprocess.Popen(
        _launch_args(executable, profile_dir, headed=headed, no_sandbox=no_sandbox),
        **popen_kwargs,
    )
    (profile_dir / "owner.json").write_text(
        json.dumps({"owner_pid": os.getpid(), "browser_pid": proc.pid, "executable": executable}),
        encoding="utf-8",
    )

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            shutil.rmtree(profile_dir, ignore_errors=True)
            hint = ""
            if sys.platform.startswith("linux") and not no_sandbox:
                hint = " (if running as root or in a container, Chromium may need --no-sandbox)"
            raise CDPError(f"Browser exited during startup with code {proc.returncode}{hint}: {executable}")
        try:
            lines = port_file.read_text(encoding="utf-8").splitlines()
            if len(lines) >= 2 and lines[0].strip().isdigit():
                return proc, f"ws://127.0.0.1:{lines[0].strip()}{lines[1].strip()}", profile_dir
        except OSError:
            pass
        time.sleep(0.05)

    _kill_tree(proc.pid)
    shutil.rmtree(profile_dir, ignore_errors=True)
    raise CDPError(f"Browser did not open a DevTools port within {timeout:.0f}s: {executable}")


# =============================================================================
# Accessibility snapshot
# =============================================================================

# Roles that get an actionable ``[ref=eN]``.
_INTERACTIVE_ROLES = frozenset({
    "button", "link", "textbox", "searchbox", "combobox", "checkbox", "radio",
    "switch", "slider", "spinbutton", "listbox", "option", "menuitem",
    "menuitemcheckbox", "menuitemradio", "tab", "treeitem", "textarea",
    "ListBoxOption", "MenuListOption", "PopUpButton", "Video", "Audio",
})
_REF_ROLES = _INTERACTIVE_ROLES | {"heading"}

# Nodes that never render a line of their own; children are promoted.
_TRANSPARENT_ROLES = frozenset({
    "generic", "none", "presentation", "InlineTextBox", "LineBreak",
    "RootWebArea", "WebArea", "Ignored", "IframePresentational", "LayoutTable",
    "LayoutTableRow", "LayoutTableCell", "Section", "GenericContainer", "Div",
})

# Structural containers worth keeping in full mode even without a name.
_STRUCTURAL_ROLES = frozenset({
    "list", "listitem", "navigation", "main", "banner", "contentinfo",
    "complementary", "region", "form", "search", "table", "row", "cell",
    "columnheader", "rowheader", "paragraph", "article", "dialog",
    "alertdialog", "menu", "menubar", "tablist", "tabpanel", "tree", "grid",
    "group", "toolbar", "figure", "blockquote",
})

_STATE_PROPS = ("checked", "selected", "expanded", "pressed", "disabled", "required", "invalid")
_MAX_NAME = 200
_MAX_TEXT = 400


def _ax_value(field: Any) -> Any:
    if isinstance(field, dict):
        return field.get("value")
    return None


def _clean(text: Any, limit: int) -> str:
    s = " ".join(str(text or "").split())
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_snapshot(nodes: List[Dict[str, Any]], *, compact: bool) -> Tuple[str, Dict[str, Dict[str, Any]]]:
    """Render an AX node list into the snapshot text + a ref table.

    Returns ``(text, refs)`` where ``refs`` maps ``"eN"`` →
    ``{"role", "name", "backendNodeId"}``. Compact mode drops unnamed
    structural wrappers and keeps only content and actionable elements.
    """
    by_id = {n.get("nodeId"): n for n in nodes}
    roots = [n for n in nodes if not n.get("parentId") or n.get("parentId") not in by_id]
    lines: List[str] = []
    refs: Dict[str, Dict[str, Any]] = {}
    seen: set = set()

    def walk(node: Dict[str, Any], depth: int, parent_name: str) -> None:
        nid = node.get("nodeId")
        if nid in seen:
            return
        seen.add(nid)
        role = str(_ax_value(node.get("role")) or "")
        name = _clean(_ax_value(node.get("name")), _MAX_NAME)
        children = [by_id[c] for c in (node.get("childIds") or []) if c in by_id]

        if node.get("ignored") or role in _TRANSPARENT_ROLES:
            for c in children:
                walk(c, depth, parent_name)
            return

        if role == "StaticText":
            text = _clean(name, _MAX_TEXT)
            # Skip text that only repeats its parent's accessible name
            # (e.g. the label inside a link or button).
            if text and not (parent_name and text in parent_name):
                prefix = "  " * depth + "- text: "
                # Inline runs (text, <a>, <code>, text) arrive as separate
                # nodes; join neighbours at the same depth into one line.
                if lines and lines[-1].startswith(prefix) and len(lines[-1]) + len(text) < len(prefix) + _MAX_TEXT:
                    lines[-1] += " " + text
                else:
                    lines.append(prefix + text)
            return

        is_ref = role in _REF_ROLES
        if not is_ref and not name and (compact or role not in _STRUCTURAL_ROLES):
            for c in children:
                walk(c, depth, parent_name)
            return

        line = "  " * depth + f"- {role}"
        if name:
            line += f" {_quote(name)}"
        if is_ref:
            ref = f"e{len(refs) + 1}"
            refs[ref] = {"role": role, "name": name, "backendNodeId": node.get("backendDOMNodeId")}
            line += f" [ref={ref}]"
        props = {p.get("name"): _ax_value(p.get("value"))
                 for p in node.get("properties") or [] if isinstance(p, dict)}
        if role == "heading" and props.get("level"):
            line += f" [level={props['level']}]"
        for key in _STATE_PROPS:
            val = props.get(key)
            if val == "mixed":
                line += f" [{key}=mixed]"
            elif val is True or val == "true":
                line += f" [{key}]"
        value = _clean(_ax_value(node.get("value")), _MAX_NAME)
        if value and value != name:
            line += f": {value}"
        lines.append(line)
        # A field's inner text node repeats its value; fold both into the
        # dedupe key its children are checked against.
        for c in children:
            walk(c, depth + 1, f"{name} {value}" if value else name)

    for r in roots:
        walk(r, 0, "")
    return "\n".join(lines), refs


# =============================================================================
# Keys
# =============================================================================

_SPECIAL_KEYS: Dict[str, Tuple[str, int, str]] = {
    # name: (code, windowsVirtualKeyCode, text)
    "Enter": ("Enter", 13, "\r"),
    "Tab": ("Tab", 9, ""),
    "Escape": ("Escape", 27, ""),
    "Backspace": ("Backspace", 8, ""),
    "Delete": ("Delete", 46, ""),
    "Space": ("Space", 32, " "),
    " ": ("Space", 32, " "),
    "ArrowUp": ("ArrowUp", 38, ""),
    "ArrowDown": ("ArrowDown", 40, ""),
    "ArrowLeft": ("ArrowLeft", 37, ""),
    "ArrowRight": ("ArrowRight", 39, ""),
    "Home": ("Home", 36, ""),
    "End": ("End", 35, ""),
    "PageUp": ("PageUp", 33, ""),
    "PageDown": ("PageDown", 34, ""),
    "Insert": ("Insert", 45, ""),
}
for _i in range(1, 13):
    _SPECIAL_KEYS[f"F{_i}"] = (f"F{_i}", 111 + _i, "")

_KEY_ALIASES = {
    "return": "Enter", "esc": "Escape", "del": "Delete", "up": "ArrowUp",
    "down": "ArrowDown", "left": "ArrowLeft", "right": "ArrowRight",
    "pgup": "PageUp", "pgdn": "PageDown", "pagedown": "PageDown", "pageup": "PageUp",
    "space": "Space", "spacebar": "Space",
}
_MODIFIERS = {"alt": 1, "option": 1, "control": 2, "ctrl": 2, "meta": 4, "cmd": 4,
              "command": 4, "super": 4, "shift": 8}


def parse_key(spec: str) -> Tuple[int, str, str, int, str]:
    """Parse ``"Control+Shift+a"`` → ``(modifiers, key, code, vk, text)``."""
    parts = [p for p in spec.replace(" + ", "+").split("+")] if spec != "+" else ["+"]
    if spec.endswith("++"):
        parts = parts[:-2] + ["+"]
    modifiers = 0
    for mod in parts[:-1]:
        bit = _MODIFIERS.get(mod.strip().lower())
        if bit is None:
            raise ValueError(f"Unknown modifier '{mod}' in key '{spec}'")
        modifiers |= bit
    key = parts[-1]
    canon = _KEY_ALIASES.get(key.lower(), key)
    for name in _SPECIAL_KEYS:
        if name.lower() == canon.lower():
            canon = name
            break
    if canon in _SPECIAL_KEYS:
        code, vk, text = _SPECIAL_KEYS[canon]
        return modifiers, (" " if canon == "Space" else canon), code, vk, text
    if len(canon) != 1:
        raise ValueError(f"Unknown key '{key}'")
    ch = canon
    if ch.isalpha():
        code, vk = f"Key{ch.upper()}", ord(ch.upper())
    elif ch.isdigit():
        code, vk = f"Digit{ch}", ord(ch)
    else:
        code, vk = "", 0
    if modifiers & 8 and ch.isalpha():
        ch = ch.upper()
    return modifiers, ch, code, vk, ch


# =============================================================================
# Page session
# =============================================================================

_ANNOTATE_JS = r"""
function(label) {
  const r = this.getBoundingClientRect();
  if (!r.width && !r.height) return false;
  const box = document.createElement('div');
  box.setAttribute('data-jettstui-annotation', '1');
  box.style.cssText = `position:absolute;left:${r.left + scrollX}px;top:${r.top + scrollY}px;` +
    `width:${r.width}px;height:${r.height}px;outline:2px solid #e11d48;z-index:2147483647;pointer-events:none;`;
  const tag = document.createElement('span');
  tag.textContent = label;
  tag.style.cssText = 'position:absolute;left:0;top:-14px;font:bold 11px/13px monospace;' +
    'background:#e11d48;color:#fff;padding:0 3px;border-radius:2px;';
  box.appendChild(tag);
  document.documentElement.appendChild(box);
  return true;
}
"""

_CLEAR_FIELD_JS = r"""
function(text) {
  if (this.tagName === 'SELECT') {
    const opt = [...this.options].find(o => o.value === text || o.text.trim() === text.trim());
    if (!opt) return 'nooption:' + [...this.options].map(o => o.text.trim()).slice(0, 30).join(' | ');
    this.value = opt.value;
    this.dispatchEvent(new Event('input', {bubbles: true}));
    this.dispatchEvent(new Event('change', {bubbles: true}));
    return 'selected';
  }
  this.focus();
  try {
    if (this.isContentEditable) {
      const range = document.createRange();
      range.selectNodeContents(this);
      const sel = getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      return 'selected-content';
    }
    if (typeof this.select === 'function') { this.select(); return 'selected-text'; }
  } catch (e) {}
  if ('value' in this) {
    this.value = '';
    this.dispatchEvent(new Event('input', {bubbles: true}));
  }
  return 'cleared';
}
"""


class NativeSession:
    """One browser page driven over CDP (owned process or attached endpoint)."""

    def __init__(self, name: str, *, cdp_url: Optional[str], headed: bool, no_sandbox: bool):
        self.name = name
        self.proc: Optional[subprocess.Popen] = None
        self.profile_dir: Optional[Path] = None
        self.owns_browser = not cdp_url
        self.created_target = False
        self.refs: Dict[str, Dict[str, Any]] = {}
        self.console: List[Dict[str, Any]] = []
        self.errors: List[Dict[str, Any]] = []
        self.lock = threading.RLock()
        self._loaded = threading.Event()
        self._loading = False
        self._main_frame: Optional[str] = None
        # Native (non-bridged) dialog currently open, if any.
        self.native_dialog: Optional[Dict[str, Any]] = None
        # Set per command by the caller: returns the CDP supervisor's pending
        # dialogs, or None when no supervisor is attached.
        self.dialog_probe: Optional[Callable[[], List[Dict[str, Any]]]] = None

        if cdp_url:
            self.ws_url = cdp_url
        else:
            self.proc, self.ws_url, self.profile_dir = launch_browser(
                session_name=name, headed=headed, no_sandbox=no_sandbox,
            )
        try:
            self.conn = CDPConnection(self.ws_url, self._on_event, local=self.owns_browser)
            self._attach()
        except Exception:
            self.close()
            raise

    # ----- wiring -------------------------------------------------------------

    def _attach(self) -> None:
        targets = self.conn.send("Target.getTargets").get("targetInfos", [])
        page = next((t for t in targets if t.get("type") == "page"), None)
        if page is None:
            self.target_id = self.conn.send("Target.createTarget", {"url": "about:blank"})["targetId"]
            self.created_target = True
        else:
            self.target_id = page["targetId"]
        self.sid = self.conn.send(
            "Target.attachToTarget", {"targetId": self.target_id, "flatten": True}
        )["sessionId"]
        for method in ("Page.enable", "Runtime.enable", "DOM.enable"):
            self.cdp(method)
        tree = self.cdp("Page.getFrameTree")
        self._main_frame = tree.get("frameTree", {}).get("frame", {}).get("id")
        # Headless Chrome advertises "HeadlessChrome" in its UA, which many
        # sites treat as a bot. Present the regular browser UA instead.
        try:
            ua = self.conn.send("Browser.getVersion").get("userAgent", "")
            if "Headless" in ua:
                self.cdp("Network.setUserAgentOverride", {"userAgent": ua.replace("HeadlessChrome", "Chrome")})
        except CDPError:
            pass

    def cdp(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 30.0,
            *, interruptible: bool = False) -> Dict[str, Any]:
        abort = self.dialog_pending if interruptible else None
        return self.conn.send(method, params, session_id=self.sid, timeout=timeout, abort=abort)

    def pending_dialogs(self) -> List[Dict[str, Any]]:
        dialogs: List[Dict[str, Any]] = []
        if self.dialog_probe is not None:
            try:
                dialogs = list(self.dialog_probe() or [])
            except Exception:
                dialogs = []
        if self.native_dialog and not dialogs:
            dialogs = [self.native_dialog]
        return dialogs

    def dialog_pending(self) -> bool:
        return bool(self.pending_dialogs())

    def alive(self) -> bool:
        if self.conn.closed:
            return False
        if self.proc is not None and self.proc.poll() is not None:
            return False
        return True

    def _on_event(self, msg: Dict[str, Any]) -> None:
        if msg.get("sessionId") != getattr(self, "sid", None):
            return
        method = msg.get("method")
        params = msg.get("params") or {}
        if method == "Page.loadEventFired":
            self._loading = False
            self._loaded.set()
        elif method == "Page.frameStartedLoading":
            if params.get("frameId") == self._main_frame:
                self._loading = True
                self._loaded.clear()
        elif method == "Page.frameStoppedLoading":
            if params.get("frameId") == self._main_frame:
                self._loading = False
                self._loaded.set()
        elif method == "Page.javascriptDialogOpening":
            self.native_dialog = {"type": params.get("type", "alert"), "message": params.get("message", "")}
            if self.dialog_probe is None:
                # Nobody can answer it (no CDP supervisor): resolve it right
                # away so the page doesn't hang. Must not block the reader.
                accept = params.get("type") in ("alert", "beforeunload")
                threading.Thread(target=self._resolve_native_dialog, args=(accept,), daemon=True).start()
        elif method == "Page.javascriptDialogClosed":
            self.native_dialog = None
        elif method == "Runtime.consoleAPICalled":
            parts = []
            for arg in params.get("args") or []:
                if "value" in arg:
                    v = arg["value"]
                    parts.append(v if isinstance(v, str) else json.dumps(v))
                else:
                    parts.append(str(arg.get("description") or arg.get("type", "")))
            self.console.append({"type": params.get("type", "log"), "text": " ".join(parts)})
            del self.console[:-500]
        elif method == "Runtime.exceptionThrown":
            det = params.get("exceptionDetails") or {}
            exc = det.get("exception") or {}
            self.errors.append({"message": str(exc.get("description") or det.get("text") or "Uncaught error")})
            del self.errors[:-200]

    def _resolve_native_dialog(self, accept: bool) -> None:
        try:
            self.cdp("Page.handleJavaScriptDialog", {"accept": accept}, timeout=5)
        except CDPError:
            pass

    # ----- helpers --------------------------------------------------------------

    def _wait_for_load(self, timeout: float) -> bool:
        from tools.interrupt import is_interrupted

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._loaded.wait(0.1):
                return True
            if is_interrupted() or self.conn.closed:
                return False
        return False

    def _settle_after_action(self, timeout: float = 10.0) -> None:
        """Give an action a moment to start a navigation, then wait for it."""
        time.sleep(0.15)
        if self._loading:
            self._wait_for_load(timeout)
            time.sleep(0.1)

    def _page_info(self) -> Dict[str, str]:
        res = self.cdp("Runtime.evaluate", {
            "expression": "({url: location.href, title: document.title})",
            "returnByValue": True,
        }, timeout=10)
        return res.get("result", {}).get("value") or {}

    def _ref_node(self, ref: str) -> int:
        key = ref.lstrip("@")
        info = self.refs.get(key)
        if not info or not info.get("backendNodeId"):
            raise CDPError(f"Unknown ref @{key}. Take a fresh browser_snapshot and use a ref from it.")
        return int(info["backendNodeId"])

    def _resolve(self, backend_id: int) -> str:
        try:
            obj = self.cdp("DOM.resolveNode", {"backendNodeId": backend_id})["object"]
        except CDPError as exc:
            raise CDPError(f"Element is no longer on the page ({exc}). Take a fresh browser_snapshot.") from exc
        return obj["objectId"]

    def _call_on(self, backend_id: int, fn: str, *args: Any, interruptible: bool = False) -> Any:
        oid = self._resolve(backend_id)
        res = self.cdp("Runtime.callFunctionOn", {
            "objectId": oid,
            "functionDeclaration": fn,
            "arguments": [{"value": a} for a in args],
            "returnByValue": True,
            "awaitPromise": True,
        }, interruptible=interruptible)
        if res.get("exceptionDetails"):
            det = res["exceptionDetails"]
            raise CDPError(str((det.get("exception") or {}).get("description") or det.get("text")))
        return res.get("result", {}).get("value")

    def _center(self, backend_id: int) -> Optional[Tuple[float, float]]:
        try:
            self.cdp("DOM.scrollIntoViewIfNeeded", {"backendNodeId": backend_id})
        except CDPError:
            pass
        try:
            quads = self.cdp("DOM.getContentQuads", {"backendNodeId": backend_id}).get("quads") or []
        except CDPError:
            return None
        for q in quads:
            xs, ys = q[0::2], q[1::2]
            if max(xs) - min(xs) >= 1 and max(ys) - min(ys) >= 1:
                return sum(xs) / 4, sum(ys) / 4
        return None

    # ----- commands -------------------------------------------------------------

    def open(self, url: str, timeout: float) -> Dict[str, Any]:
        self._loaded.clear()
        self._loading = True
        res = self.cdp("Page.navigate", {"url": url}, timeout=timeout, interruptible=True)
        if res.get("errorText"):
            self._loading = False
            return {"success": False, "error": f"Navigation to {url} failed: {res['errorText']}"}
        if res.get("loaderId"):
            if not self._wait_for_load(max(1.0, timeout - 1)):
                state = self.cdp("Runtime.evaluate", {"expression": "document.readyState", "returnByValue": True})
                if state.get("result", {}).get("value") == "loading":
                    return {"success": False, "error": f"Page did not finish loading within {timeout:.0f}s: {url}"}
        else:
            self._loading = False
        time.sleep(0.2)  # let client-side frameworks render first paint
        info = self._page_info()
        return {"success": True, "data": {"url": info.get("url", url), "title": info.get("title", "")}}

    def snapshot(self, compact: bool) -> Dict[str, Any]:
        nodes = self.cdp("Accessibility.getFullAXTree", {}, timeout=30).get("nodes", [])
        text, refs = build_snapshot(nodes, compact=compact)
        self.refs = refs
        return {"success": True, "data": {
            "snapshot": text,
            "refs": {k: {"role": v["role"], "name": v["name"]} for k, v in refs.items()},
        }}

    def click(self, ref: str) -> Dict[str, Any]:
        node = self._ref_node(ref)
        point = self._center(node)
        if point is None:
            # Zero-size / hidden element: fall back to a DOM-level click.
            self._call_on(node, "function(){ this.click(); }", interruptible=True)
        else:
            x, y = point
            for ev, extra in (("mouseMoved", {}),
                              ("mousePressed", {"button": "left", "clickCount": 1, "buttons": 1}),
                              ("mouseReleased", {"button": "left", "clickCount": 1})):
                self.cdp("Input.dispatchMouseEvent", {"type": ev, "x": x, "y": y, **extra}, interruptible=True)
        self._settle_after_action()
        return {"success": True, "data": {"clicked": ref}}

    def fill(self, ref: str, text: str) -> Dict[str, Any]:
        node = self._ref_node(ref)
        try:
            self.cdp("DOM.focus", {"backendNodeId": node})
        except CDPError:
            point = self._center(node)
            if point:
                x, y = point
                self.cdp("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
                self.cdp("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
        state = self._call_on(node, _CLEAR_FIELD_JS, text)
        if isinstance(state, str) and state.startswith("nooption:"):
            return {"success": False, "error": f"No option matching '{text}'. Options: {state[9:]}"}
        if state == "selected":
            return {"success": True, "data": {}}
        if text:
            self.cdp("Input.insertText", {"text": text}, interruptible=True)
        elif state in ("selected-text", "selected-content"):
            self._key("Delete")
        return {"success": True, "data": {}}

    def _key(self, spec: str) -> None:
        modifiers, key, code, vk, text = parse_key(spec)
        # Shortcuts (Ctrl/Alt/Meta) must not insert their character.
        if modifiers & (1 | 2 | 4):
            text = ""
        base = {"modifiers": modifiers, "key": key, "code": code,
                "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk}
        down = {"type": "keyDown" if text else "rawKeyDown", **base}
        if text:
            down["text"] = text
            down["unmodifiedText"] = text
        self.cdp("Input.dispatchKeyEvent", down, interruptible=True)
        self.cdp("Input.dispatchKeyEvent", {"type": "keyUp", **base}, interruptible=True)

    def press(self, key: str) -> Dict[str, Any]:
        try:
            self._key(key)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        self._settle_after_action()
        return {"success": True, "data": {}}

    def scroll(self, direction: str, pixels: int) -> Dict[str, Any]:
        metrics = self.cdp("Page.getLayoutMetrics")
        vp = metrics.get("cssLayoutViewport") or metrics.get("layoutViewport") or {}
        x = float(vp.get("clientWidth", 1280)) / 2
        y = float(vp.get("clientHeight", 900)) / 2
        dx, dy = {"up": (0, -pixels), "down": (0, pixels),
                  "left": (-pixels, 0), "right": (pixels, 0)}.get(direction, (0, pixels))
        self.cdp("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": x, "y": y, "deltaX": dx, "deltaY": dy})
        time.sleep(0.15)
        return {"success": True, "data": {}}

    def back(self, timeout: float) -> Dict[str, Any]:
        hist = self.cdp("Page.getNavigationHistory")
        idx = hist.get("currentIndex", 0)
        entries = hist.get("entries", [])
        if idx <= 0 or not entries:
            return {"success": False, "error": "No previous page in history"}
        self._loaded.clear()
        self._loading = True
        self.cdp("Page.navigateToHistoryEntry", {"entryId": entries[idx - 1]["id"]})
        self._wait_for_load(timeout)
        self._loading = False
        info = self._page_info()
        return {"success": True, "data": {"url": info.get("url", ""), "title": info.get("title", "")}}

    def evaluate(self, expression: str, timeout: float) -> Dict[str, Any]:
        params = {"expression": expression, "returnByValue": True, "awaitPromise": True,
                  "userGesture": True, "replMode": True}
        res = self.cdp("Runtime.evaluate", params, timeout=timeout, interruptible=True)
        if res.get("exceptionDetails"):
            det = res["exceptionDetails"]
            msg = (det.get("exception") or {}).get("description") or det.get("text") or "JavaScript error"
            return {"success": False, "error": str(msg)}
        result = res.get("result", {})
        if "value" in result:
            value = result["value"]
        elif result.get("type") == "undefined":
            value = None
        else:
            value = result.get("description") or result.get("unserializableValue")
        return {"success": True, "data": {"result": value}}

    def screenshot(self, path: str, *, full: bool, annotate: bool) -> Dict[str, Any]:
        annotations: List[Dict[str, Any]] = []
        if annotate:
            if not self.refs:
                self.snapshot(compact=True)
            for i, (ref, info) in enumerate(list(self.refs.items())[:300], start=1):
                try:
                    if self._call_on(int(info["backendNodeId"]), _ANNOTATE_JS, f"[{i}]"):
                        annotations.append({"number": i, "ref": f"@{ref}", "role": info["role"], "name": info["name"]})
                except (CDPError, KeyError, TypeError, ValueError):
                    continue
        params: Dict[str, Any] = {"format": "png"}
        try:
            if full:
                size = self.cdp("Page.getLayoutMetrics").get("cssContentSize") or {}
                width = max(1, int(size.get("width", 1280)))
                height = max(1, min(int(size.get("height", 900)), 16000))
                params.update({"captureBeyondViewport": True,
                               "clip": {"x": 0, "y": 0, "width": width, "height": height, "scale": 1}})
            data = self.cdp("Page.captureScreenshot", params, timeout=60)["data"]
        finally:
            if annotate:
                try:
                    self.cdp("Runtime.evaluate", {"expression":
                        "document.querySelectorAll('[data-jettstui-annotation]').forEach(e => e.remove())"})
                except CDPError:
                    pass
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(base64.b64decode(data))
        result: Dict[str, Any] = {"path": str(out)}
        if annotate:
            result["annotations"] = annotations
        return {"success": True, "data": result}

    def close(self) -> None:
        conn = getattr(self, "conn", None)
        if self.owns_browser:
            if conn is not None and not conn.closed:
                try:
                    conn.send("Browser.close", timeout=5)
                except CDPError:
                    pass
            if self.proc is not None:
                graceful = conn is not None and not conn.closed
                try:
                    if not graceful:
                        raise TimeoutError
                    self.proc.wait(timeout=5)
                except Exception:
                    _kill_tree(self.proc.pid)
            if self.profile_dir is not None:
                for _ in range(10):  # Windows keeps profile files locked briefly
                    shutil.rmtree(self.profile_dir, ignore_errors=True)
                    if not self.profile_dir.exists():
                        break
                    time.sleep(0.2)
        elif conn is not None and not conn.closed:
            try:
                if self.created_target:
                    conn.send("Target.closeTarget", {"targetId": self.target_id}, timeout=5)
                else:
                    conn.send("Target.detachFromTarget", {"sessionId": self.sid}, timeout=5)
            except (CDPError, AttributeError):
                pass
        if conn is not None:
            conn.close()


# =============================================================================
# Session registry + command dispatch
# =============================================================================

_sessions: Dict[str, NativeSession] = {}
_sessions_lock = threading.Lock()


def get_session_ws_url(session_name: str) -> Optional[str]:
    """Browser-level DevTools URL of a live native session (for the CDP supervisor)."""
    with _sessions_lock:
        sess = _sessions.get(session_name)
    if sess is None or not sess.alive():
        return None
    return sess.ws_url


def has_session(session_name: str) -> bool:
    with _sessions_lock:
        return session_name in _sessions


def _get_or_create(session_info: Dict[str, Any], *, headed: bool, no_sandbox: bool) -> NativeSession:
    name = str(session_info.get("session_name") or "default")
    with _sessions_lock:
        sess = _sessions.get(name)
    if sess is not None and sess.alive():
        return sess
    if sess is not None:
        logger.info("native browser session %s died; relaunching", name)
        try:
            sess.close()
        except Exception:
            pass
    sess = NativeSession(name, cdp_url=session_info.get("cdp_url") or None,
                         headed=headed, no_sandbox=no_sandbox)
    with _sessions_lock:
        existing = _sessions.get(name)
        if existing is not None and existing.alive():
            sess.close()
            return existing
        _sessions[name] = sess
    return sess


def close_session(session_name: str) -> None:
    with _sessions_lock:
        sess = _sessions.pop(session_name, None)
    if sess is not None:
        sess.close()


def close_all() -> None:
    with _sessions_lock:
        sessions = list(_sessions.values())
        _sessions.clear()
    for sess in sessions:
        try:
            sess.close()
        except Exception:
            pass


atexit.register(close_all)


def _parse_screenshot_args(args: List[str]) -> Tuple[str, bool, bool]:
    full = "--full" in args
    annotate = "--annotate" in args
    paths = [a for a in args if not a.startswith("--")]
    path = paths[-1] if paths else os.path.join(tempfile.gettempdir(), f"jettstui_shot_{uuid.uuid4().hex[:8]}.png")
    return path, full, annotate


def _describe_dialog(dialog: Dict[str, Any]) -> str:
    kind = dialog.get("type") or "alert"
    message = _clean(dialog.get("message"), 200)
    return f"JavaScript {kind} dialog" + (f' "{message}"' if message else "")


def run_command(session_info: Dict[str, Any], command: str, args: Optional[List[str]] = None,
                timeout: float = 30.0, *, headed: bool = False, no_sandbox: bool = False,
                dialog_probe: Optional[Callable[[], List[Dict[str, Any]]]] = None) -> Dict[str, Any]:
    """Execute one ``agent-browser``-style command natively. Never raises.

    ``dialog_probe`` returns the CDP supervisor's pending dialogs. While one
    is open the renderer is frozen, so commands fail fast (and snapshots
    describe the dialog) instead of hanging until the timeout.
    """
    args = list(args or [])
    name = str(session_info.get("session_name") or "default")

    if command == "close":
        try:
            close_session(name)
        except Exception as exc:
            logger.debug("native close of %s failed: %s", name, exc)
        return {"success": True, "data": {}}
    if command == "record":
        return {"success": False, "error": "Session recording is not supported by the native browser driver"}

    try:
        sess = _get_or_create(session_info, headed=headed, no_sandbox=no_sandbox)
    except Exception as exc:
        return {"success": False, "error": f"Failed to start browser: {exc}"}

    sess.dialog_probe = dialog_probe
    dialogs = sess.pending_dialogs()
    if dialogs and command not in ("console", "errors"):
        desc = _describe_dialog(dialogs[0])
        if command == "snapshot":
            sess.refs = {}
            return {"success": True, "data": {
                "snapshot": f"- dialog: {desc} is open and blocks the page. Respond with browser_dialog first.",
                "refs": {},
                "pending_dialogs": dialogs,
            }}
        return {"success": False, "error": f"A {desc} is open and blocks the page. Respond with browser_dialog first."}

    try:
        with sess.lock:
            if command == "open":
                return sess.open(args[0] if args else "about:blank", timeout)
            if command == "snapshot":
                return sess.snapshot(compact="-c" in args or "--compact" in args)
            if command == "click":
                return sess.click(args[0])
            if command == "fill":
                return sess.fill(args[0], args[1] if len(args) > 1 else "")
            if command == "press":
                return sess.press(args[0])
            if command == "scroll":
                pixels = int(args[1]) if len(args) > 1 and str(args[1]).isdigit() else 500
                return sess.scroll(args[0] if args else "down", pixels)
            if command == "back":
                return sess.back(timeout)
            if command == "eval":
                return sess.evaluate(args[0] if args else "undefined", timeout)
            if command == "console":
                messages = list(sess.console)
                if "--clear" in args:
                    sess.console.clear()
                return {"success": True, "data": {"messages": messages}}
            if command == "errors":
                errors = list(sess.errors)
                if "--clear" in args:
                    sess.errors.clear()
                return {"success": True, "data": {"errors": errors}}
            if command == "screenshot":
                path, full, annotate = _parse_screenshot_args(args)
                return sess.screenshot(path, full=full, annotate=annotate)
            return {"success": False, "error": f"Unknown browser command '{command}'"}
    except DialogBlocked:
        dialogs = sess.pending_dialogs()
        desc = _describe_dialog(dialogs[0]) if dialogs else "JavaScript dialog"
        if command in ("click", "press", "fill"):
            # The action itself happened; it just opened a dialog.
            return {"success": True, "data": {"dialog_opened": dialogs[0] if dialogs else {}},
                    "warning": f"The action opened a {desc}. Respond with browser_dialog."}
        return {"success": False, "error": f"A {desc} opened and blocks the page. Respond with browser_dialog."}
    except CDPError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.warning("native browser '%s' failed: %s", command, exc, exc_info=True)
        return {"success": False, "error": str(exc)}
