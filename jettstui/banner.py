"""Welcome banner, ASCII art, skills summary, and update check for the CLI.

Pure display functions with no JettsTUICLI state dependency.
"""
import json
import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlparse
from jettstui_constants import get_jettstui_home
from typing import TYPE_CHECKING, Dict, List, Optional

from jettstui import rice

# rich and prompt_toolkit are imported lazily (inside the functions that use
# them) rather than at module level.  Importing this module is on the TUI
# gateway's critical startup path purely to reach the lightweight update-check
# helpers (``prefetch_update_check``); pulling rich.console + prompt_toolkit
# eagerly added ~50ms of wasted imports before ``gateway.ready`` could fire.
# Keep the type-only reference available to checkers without the runtime cost.
if TYPE_CHECKING:
    from rich.console import Console

logger = logging.getLogger(__name__)


# =========================================================================
# ANSI building blocks for conversation display
# =========================================================================

_GOLD = "\033[1;38;2;255;215;0m"  # True-color #FFD700 bold
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RST = "\033[0m"


def cprint(text: str):
    """Print ANSI-colored text through prompt_toolkit's renderer."""
    from prompt_toolkit import print_formatted_text as _pt_print
    from prompt_toolkit.formatted_text import ANSI as _PT_ANSI
    _pt_print(_PT_ANSI(text))


# =========================================================================
# Skin-aware color helpers
# =========================================================================

def _skin_color(key: str, fallback: str) -> str:
    """Get a color from the active skin, or return fallback."""
    try:
        from jettstui.skin_engine import get_active_skin
        return get_active_skin().get_color(key, fallback)
    except Exception:
        return fallback
# =========================================================================
# ASCII Art & Branding
# =========================================================================

from jettstui import __version__ as VERSION, __release_date__ as RELEASE_DATE

JETTSTUI_AGENT_LOGO = """[bold #cba6f7]╭──────────────────────────────╮[/]
[bold #b9a9fb]│                              │[/]
[#b4befe]│          JETTS-TUI           │[/]
[#a6b8fc]│                              │[/]
[#89b4fa]│     YOUR AI WORKSPACE        │[/]
[#89dceb]╰──────────────────────────────╯[/]"""

# Abstract prism emblem — a violet→sky gradient diamond that matches the
# wordmark. Replaces the old winged-staff mascot, which carried upstream
# symbolism; this one is pure JettsTUI.
JETTSTUI_CADUCEUS = """[#cba6f7]          ╱╲          [/]
[#c0a9f8]         ╱  ╲         [/]
[#b4befe]        ╱ ╱╲ ╲        [/]
[#adbafd]       ╱ ╱  ╲ ╲       [/]
[#a6b8fc]      ╱ ╱ ╱╲ ╲ ╲      [/]
[#9fb6fb]     ◈─╱─╱  ╲─╲─◈     [/]
[#98b5fb]      ╲ ╲ ╲╱ ╱ ╱      [/]
[#91b4fa]       ╲ ╲  ╱ ╱       [/]
[#89b4fa]        ╲ ╲╱ ╱        [/]
[#84c1ef]         ╲  ╱         [/]
[#89dceb]          ╲╱          [/]"""



# =========================================================================
# Skills scanning
# =========================================================================

def get_available_skills() -> Dict[str, List[str]]:
    """Return skills grouped by category, filtered by platform and disabled state.

    Delegates to ``_find_all_skills()`` from ``tools/skills_tool`` which already
    handles platform gating (``platforms:`` frontmatter) and respects the
    user's ``skills.disabled`` config list.
    """
    try:
        from tools.skills_tool import _find_all_skills
        all_skills = _find_all_skills()  # already filtered
    except Exception:
        return {}

    skills_by_category: Dict[str, List[str]] = {}
    for skill in all_skills:
        category = skill.get("category") or "general"
        skills_by_category.setdefault(category, []).append(skill["name"])
    return skills_by_category


# =========================================================================
# Update check
# =========================================================================

# Cache update check results for 6 hours to avoid repeated git fetches
_UPDATE_CHECK_CACHE_SECONDS = 6 * 3600

# Sentinel returned when we know an update exists but can't count commits
# (e.g. nix-built jettstui — no local git history to count against).
UPDATE_AVAILABLE_NO_COUNT = -1

_UPSTREAM_REPO_URL = "https://github.com/Raioshok/JETTS-TUI.git"
_OFFICIAL_REPO_CANONICAL = "github.com/raioshok/jetts-tui"


def _canonical_github_remote(url: str | None) -> str:
    """Return ``host/owner/repo`` for common GitHub remote URL forms."""
    if not url:
        return ""
    value = url.strip()
    if value.startswith("git@github.com:"):
        value = "github.com/" + value[len("git@github.com:"):]
    elif value.startswith("ssh://git@github.com/"):
        value = "github.com/" + value[len("ssh://git@github.com/"):]
    else:
        parsed = urlparse(value)
        if parsed.netloc and parsed.path:
            value = f"{parsed.netloc}{parsed.path}"
    value = value.strip().rstrip("/")
    if value.endswith(".git"):
        value = value[:-4]
    return value.lower()


def _is_ssh_remote(url: str | None) -> bool:
    if not url:
        return False
    value = url.strip().lower()
    return value.startswith("git@") or value.startswith("ssh://")


def _is_official_ssh_remote(url: str | None) -> bool:
    return _is_ssh_remote(url) and _canonical_github_remote(url) == _OFFICIAL_REPO_CANONICAL


def _git_stdout(args: list[str], *, cwd: Path, timeout: int = 5) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            # git output is UTF-8; on Windows text=True defaults to the ANSI
            # code page and bytes like 0x90 (3rd byte of 🐛 in a commit
            # subject) crash the stdlib reader thread (#52649).
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=str(cwd),
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return (result.stdout or "").strip()


def _check_via_rev(local_rev: str) -> Optional[int]:
    """Compare an embedded git revision to upstream main via ls-remote.

    Returns 0 if up-to-date, ``UPDATE_AVAILABLE_NO_COUNT`` if behind,
    or ``None`` on failure.
    """
    try:
        result = subprocess.run(
            ["git", "ls-remote", _UPSTREAM_REPO_URL, "refs/heads/main"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=10,
        )
    except Exception:
        return None
    if result.returncode != 0 or not result.stdout:
        return None
    upstream_rev = result.stdout.split()[0]
    if not upstream_rev:
        return None
    return 0 if upstream_rev == local_rev else UPDATE_AVAILABLE_NO_COUNT


def _check_via_local_git(repo_dir: Path) -> Optional[int]:
    """Count commits behind origin/main in a local checkout."""
    origin_url = _git_stdout(["remote", "get-url", "origin"], cwd=repo_dir)
    if _is_official_ssh_remote(origin_url):
        head_rev = _git_stdout(["rev-parse", "HEAD"], cwd=repo_dir)
        checked = _check_via_rev(head_rev) if head_rev else None
        if checked == UPDATE_AVAILABLE_NO_COUNT:
            return 1
        return checked

    # Installer checkouts are shallow (`git clone --depth 1`). On a shallow
    # clone the history stops at a single commit, so a plain `git fetch` would
    # unshallow the repo (dragging in the whole history) and
    # `rev-list --count HEAD..origin/main` would report a huge bogus "behind"
    # number (e.g. "12492 commits behind"). Detect shallow up front: fetch with
    # --depth 1 to preserve the boundary and compare tip SHAs instead of
    # counting. Full clones (developers, Docker dev images) keep the exact
    # count path unchanged. Mirrors the desktop fix in apps/desktop/electron/main.cjs.
    shallow = _git_stdout(["rev-parse", "--is-shallow-repository"], cwd=repo_dir)
    is_shallow = shallow == "true"

    try:
        fetch_args = ["git", "fetch", "origin"]
        if is_shallow:
            fetch_args += ["--depth", "1"]
        fetch_args.append("--quiet")
        subprocess.run(
            fetch_args,
            capture_output=True, timeout=10,
            cwd=str(repo_dir),
        )
    except Exception:
        pass  # Offline or timeout — use stale refs, that's fine

    if is_shallow:
        # No history to count across the shallow boundary. `origin/main` may not
        # be a tracking ref in a `clone --depth 1`, so prefer FETCH_HEAD (just
        # updated by the fetch above) and fall back to origin/main.
        head_rev = _git_stdout(["rev-parse", "HEAD"], cwd=repo_dir)
        target_rev = (
            _git_stdout(["rev-parse", "FETCH_HEAD"], cwd=repo_dir)
            or _git_stdout(["rev-parse", "origin/main"], cwd=repo_dir)
        )
        if not head_rev or not target_rev:
            return None
        return 0 if head_rev == target_rev else UPDATE_AVAILABLE_NO_COUNT

    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD..origin/main"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=5,
            cwd=str(repo_dir),
        )
        if result.returncode == 0:
            return int(result.stdout.strip())
    except Exception:
        pass
    return None


def check_for_updates() -> Optional[int]:
    """Check whether a JettsTUI update is available.

    Two paths: if ``JETTSTUI_REVISION`` is set (nix builds embed it), compare
    it to upstream main via ``git ls-remote``. Otherwise look for a local
    git checkout and count commits behind ``origin/main``.

    Returns the number of commits behind, ``UPDATE_AVAILABLE_NO_COUNT`` (-1)
    if behind but the count is unknown, ``0`` if up-to-date, or ``None`` if
    the check failed or doesn't apply. Cached for 6 hours.
    """
    jettstui_home = get_jettstui_home()
    cache_file = jettstui_home / ".update_check"
    embedded_rev = os.environ.get("JETTSTUI_REVISION") or None

    # Docker images have no working tree to count commits against — the
    # published image excludes `.git` (see .dockerignore) and sets no
    # JETTSTUI_REVISION (that's nix-only). Returning None makes both the Rich
    # banner (build_welcome_banner) and the Ink badge (branding.tsx, guarded
    # on `typeof === 'number' && > 0`) show nothing. The dashboard's REST
    # `/api/jettstui/update/check` endpoint short-circuits docker the same way
    # (web_server.py); mirror that here so the banner/TUI surfaces agree.
    try:
        from jettstui.config import detect_install_method, get_project_root
        if detect_install_method(get_project_root()) == "docker":
            return None
    except Exception:
        pass

    # Read cache — invalidate if the embedded rev OR installed version has
    # changed since the last check.
    now = time.time()
    try:
        if cache_file.exists():
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if (
                now - cached.get("ts", 0) < _UPDATE_CHECK_CACHE_SECONDS
                and cached.get("rev") == embedded_rev
                and cached.get("ver") == VERSION
            ):
                return cached.get("behind")
    except Exception:
        pass

    if embedded_rev:
        behind = _check_via_rev(embedded_rev)
    else:
        # Prefer the running code's location over the profile-scoped path.
        # $JETTSTUI_HOME/jettstui/ may be a stale copy from --clone-all;
        # Path(__file__) always resolves to the actual installed checkout.
        repo_dir = Path(__file__).parent.parent.resolve()
        if not (repo_dir / ".git").exists():
            repo_dir = jettstui_home / "jettstui"
        if not (repo_dir / ".git").exists():
            # No git checkout and no embedded revision — can't determine
            # update status. This is the Docker path (already short-circuited
            # above) or an unsupported install without a source tree.
            behind = None
        else:
            behind = _check_via_local_git(repo_dir)

    try:
        cache_file.write_text(
            json.dumps({"ts": now, "behind": behind, "rev": embedded_rev, "ver": VERSION}),
            encoding="utf-8",
        )
    except Exception:
        pass

    return behind


def _resolve_repo_dir() -> Optional[Path]:
    """Return the active JettsTUI git checkout, or None if this isn't a git install.

    Prefers the running code's location over the profile-scoped path
    because ``$JETTSTUI_HOME/jettstui/`` may be a stale copy carried
    over by ``--clone-all``.
    """
    repo_dir = Path(__file__).parent.parent.resolve()
    if not (repo_dir / ".git").exists():
        jettstui_home = get_jettstui_home()
        repo_dir = jettstui_home / "jettstui"
    return repo_dir if (repo_dir / ".git").exists() else None


def _git_short_hash(repo_dir: Path, rev: str) -> Optional[str]:
    """Resolve a git revision to an 8-character short hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=8", rev],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            cwd=str(repo_dir),
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    value = (result.stdout or "").strip()
    return value or None


def get_git_banner_state(repo_dir: Optional[Path] = None) -> Optional[dict]:
    """Return upstream/local git hashes for the startup banner.

    For source installs and dev images this runs ``git rev-parse`` against
    the active checkout.  When no checkout is available — the canonical case
    is the published Docker image, which excludes ``.git`` from the build
    context — we fall back to the baked-in build SHA (see
    ``jettstui/build_info.py``) and return it as a frozen
    ``upstream == local`` state with ``ahead=0``.  A built image is by
    definition pinned to one commit, so "ahead" is always zero and the
    banner correctly shows ``· upstream <sha>`` with no carried-commits
    annotation.
    """
    repo_dir = repo_dir or _resolve_repo_dir()
    if repo_dir is None:
        # No git checkout — try the baked build SHA (Docker image path).
        try:
            from jettstui.build_info import get_build_sha
            baked = get_build_sha(short=8)
            if baked:
                return {"upstream": baked, "local": baked, "ahead": 0}
        except Exception:
            pass
        return None

    upstream = _git_short_hash(repo_dir, "origin/main")
    local = _git_short_hash(repo_dir, "HEAD")
    if not upstream or not local:
        # Live-git lookup failed (e.g. shallow clone without origin/main).
        # Fall back to the baked build SHA if available.
        try:
            from jettstui.build_info import get_build_sha
            baked = get_build_sha(short=8)
            if baked:
                return {"upstream": baked, "local": baked, "ahead": 0}
        except Exception:
            pass
        return None

    ahead = 0
    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", "origin/main..HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            cwd=str(repo_dir),
        )
        if result.returncode == 0:
            ahead = int((result.stdout or "0").strip() or "0")
    except Exception:
        ahead = 0

    return {"upstream": upstream, "local": local, "ahead": max(ahead, 0)}


_RELEASE_URL_BASE = "https://github.com/Raioshok/JETTS-TUI/releases/tag"
_latest_release_cache: Optional[tuple] = None  # (tag, url) once resolved


def get_latest_release_tag(repo_dir: Optional[Path] = None) -> Optional[tuple]:
    """Return ``(tag, release_url)`` for the latest git tag, or None.

    Local-only — runs ``git describe --tags --abbrev=0`` against the
    JettsTUI checkout. Cached per-process. Release URL always points at the
    canonical JettsTUI repo (forks don't get a link).
    """
    global _latest_release_cache
    if _latest_release_cache is not None:
        return _latest_release_cache or None

    repo_dir = repo_dir or _resolve_repo_dir()
    if repo_dir is None:
        _latest_release_cache = ()  # falsy sentinel — skip future lookups
        return None

    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
            cwd=str(repo_dir),
        )
    except Exception:
        _latest_release_cache = ()
        return None

    if result.returncode != 0:
        _latest_release_cache = ()
        return None

    tag = (result.stdout or "").strip()
    if not tag:
        _latest_release_cache = ()
        return None

    url = f"{_RELEASE_URL_BASE}/{tag}"
    _latest_release_cache = (tag, url)
    return _latest_release_cache


def format_banner_version_label() -> str:
    """Return the version label shown in the startup banner title."""
    base = f"JettsTUI v{VERSION} ({RELEASE_DATE})"
    state = get_git_banner_state()
    if not state:
        return base

    upstream = state["upstream"]
    local = state["local"]
    ahead = int(state.get("ahead") or 0)

    if ahead <= 0 or upstream == local:
        return f"{base} · upstream {upstream}"

    carried_word = "commit" if ahead == 1 else "commits"
    return f"{base} · upstream {upstream} · local {local} (+{ahead} carried {carried_word})"


# =========================================================================
# Non-blocking update check
# =========================================================================

_update_result: Optional[int] = None
_update_check_done = threading.Event()


def prefetch_update_check():
    """Kick off update check in a background daemon thread."""
    def _run():
        global _update_result
        _update_result = check_for_updates()
        _update_check_done.set()
    t = threading.Thread(target=_run, daemon=True)
    t.start()


def get_update_result(timeout: float = 0.5) -> Optional[int]:
    """Get result of prefetched check. Returns None if not ready."""
    _update_check_done.wait(timeout=timeout)
    return _update_result


# =========================================================================
# Welcome banner
# =========================================================================

def _format_context_length(tokens: int) -> str:
    """Format a token count for display (e.g. 128000 → '128K', 1048576 → '1M')."""
    if tokens >= 1_000_000:
        val = tokens / 1_000_000
        rounded = round(val)
        if abs(val - rounded) < 0.05:
            return f"{rounded}M"
        return f"{val:.1f}M"
    elif tokens >= 1_000:
        val = tokens / 1_000
        rounded = round(val)
        if abs(val - rounded) < 0.05:
            return f"{rounded}K"
        return f"{val:.1f}K"
    return str(tokens)


def _display_toolset_name(toolset_name: str) -> str:
    """Normalize internal/legacy toolset identifiers for banner display."""
    if not toolset_name:
        return "unknown"
    return (
        toolset_name[:-6]
        if toolset_name.endswith("_tools")
        else toolset_name
    )


def build_welcome_banner(console: "Console", model: str, cwd: str,
                         tools: List[dict] = None,
                         enabled_toolsets: List[str] = None,
                         session_id: str = None,
                         get_toolset_for_tool=None,
                         context_length: int = None,
                         provider: str = None):
    """Build and print a welcome banner with the emblem on left and info on right.

    Args:
        console: Rich Console instance.
        model: Current model name.
        cwd: Current working directory.
        tools: List of tool definitions.
        enabled_toolsets: List of enabled toolset names.
        session_id: Session identifier.
        get_toolset_for_tool: Callable to map tool name -> toolset name.
        context_length: Model's context window size in tokens.
        provider: Active provider id. When ``"moa"``, ``model`` is a MoA
            preset name and the banner renders the aggregator instead of a
            bare model slug.
    """
    from model_tools import check_tool_availability, TOOLSET_REQUIREMENTS
    from rich.panel import Panel
    from rich.table import Table
    if get_toolset_for_tool is None:
        from model_tools import get_toolset_for_tool

    tools = tools or []
    enabled_toolsets = enabled_toolsets or []

    _, unavailable_toolsets = check_tool_availability(quiet=True)
    # The availability check walks the GLOBAL toolset registry, so it includes
    # toolsets that aren't part of this agent's platform set at all (e.g.
    # `discord`, `feishu_doc` on a CLI session). Those must never surface in the
    # banner's "Available Tools" — they aren't exposed to the agent. Restrict to
    # toolsets actually enabled for this agent; a toolset that's enabled but
    # currently has unmet deps legitimately shows as disabled/lazy below.
    _enabled_ts = {str(t) for t in enabled_toolsets}
    if _enabled_ts:
        unavailable_toolsets = [
            item for item in unavailable_toolsets
            if str(item.get("id", item.get("name", ""))) in _enabled_ts
        ]
    disabled_tools = set()
    # Tools whose toolset has a check_fn are lazy-initialized (e.g. honcho,
    # homeassistant) — they show as unavailable at banner time because the
    # check hasn't run yet, but they aren't misconfigured.
    lazy_tools = set()
    for item in unavailable_toolsets:
        toolset_name = item.get("name", "")
        ts_req = TOOLSET_REQUIREMENTS.get(toolset_name, {})
        tools_in_ts = item.get("tools", [])
        if ts_req.get("check_fn"):
            lazy_tools.update(tools_in_ts)
        else:
            disabled_tools.update(tools_in_ts)

    from rich.panel import Panel
    from rich.table import Table
    from rich.console import Group
    from rich.rule import Rule
    from rich.text import Text
    from rich.align import Align
    from rich import box
    from rich.markup import escape

    # ── Palette (Catppuccin Mocha, violet accent) ────────────────────────
    accent = _skin_color("banner_accent", "#cba6f7")
    dim = _skin_color("banner_dim", "#7f849c")
    text = _skin_color("banner_text", "#cdd6f4")
    title_color = _skin_color("banner_title", "#b4befe")
    border_color = _skin_color("banner_border", "#585b70")

    try:
        from jettstui.skin_engine import get_active_skin
        _bskin = get_active_skin()
    except Exception:
        _bskin = None

    # ── Counts, not walls ────────────────────────────────────────────────
    toolsets_dict: Dict[str, list] = {}
    for tool in tools:
        tname = tool["function"]["name"]
        ts = _display_toolset_name(get_toolset_for_tool(tname) or "other")
        toolsets_dict.setdefault(ts, []).append(tname)
    for item in unavailable_toolsets:
        dn = _display_toolset_name(item.get("id", item.get("name", "unknown")))
        toolsets_dict.setdefault(dn, [])
        for tname in item.get("tools", []):
            if tname not in toolsets_dict[dn]:
                toolsets_dict[dn].append(tname)
    toolset_names = sorted(toolsets_dict)

    try:
        from tools.mcp_tool import get_mcp_status
        mcp_status = get_mcp_status()
    except Exception:
        mcp_status = []
    mcp_connected = sum(1 for s in mcp_status if s.get("connected")) if mcp_status else 0

    _skills_enabled = (not _enabled_ts) or ("skills" in _enabled_ts)
    if _skills_enabled:
        skills_by_category = get_available_skills()
        total_skills = sum(len(s) for s in skills_by_category.values())
    else:
        total_skills = 0

    try:
        from jettstui.models import CANONICAL_PROVIDERS as _CP
        n_providers = len(_CP)
    except Exception:
        n_providers = 0

    # ── Model / provider label ───────────────────────────────────────────
    if (provider or "").strip().lower() == "moa":
        model_short = model
        prov_label = "MoA"
    else:
        model_short = model.split("/")[-1] if "/" in model else model
        if model_short.endswith(".gguf"):
            model_short = model_short[:-5]
        prov_label = (provider or "").strip()
    if len(model_short) > 36:
        model_short = model_short[:33] + "..."
    model_short = escape(model_short)
    prov_label = escape(prov_label)

    # Fold $HOME to ~ and clip a long cwd so the line never wraps.
    _cwd = cwd
    try:
        _home = str(Path.home())
        if _cwd.startswith(_home):
            _cwd = "~" + _cwd[len(_home):]
    except Exception:
        pass
    if len(_cwd) > 44:
        _cwd = "..." + _cwd[-41:]
    _cwd = escape(_cwd)

    # ── Aligned fact rows ────────────────────────────────────────────────
    facts = Table.grid(padding=(0, 1))
    facts.add_column(justify="center", width=1)
    facts.add_column(justify="left", width=8)
    facts.add_column(justify="left")

    def _fact(glyph: str, label: str, value_markup: str) -> None:
        facts.add_row(f"[{accent}]{glyph}[/]", f"[{dim}]{label}[/]", value_markup)

    _prov = f"  [{dim}]·[/]  [{dim}]{prov_label}[/]" if prov_label else ""
    _fact("◆", "model", f"[bold {text}]{model_short}[/]{_prov}")
    if context_length:
        _fact("◈", "context", f"[{text}]{_format_context_length(context_length)} tokens[/]")
    _fact("▸", "cwd", f"[{text}]{_cwd}[/]")
    if session_id:
        _fact("⟩", "session", f"[{dim}]{escape(session_id)}[/]")
    if os.getenv("JETTSTUI_YOLO_MODE"):
        _fact("⚠", "mode", "[bold red]YOLO — approvals bypassed[/]")

    # ── Toolset chips (names only — no per-tool wall) ────────────────────
    chip_line = None
    if toolset_names:
        shown = toolset_names[:8]
        more = len(toolset_names) - len(shown)
        chips = f"[{dim}] · [/]".join(f"[{text}]{t}[/]" for t in shown)
        if more > 0:
            chips += f"[{dim}] · +{more}[/]"
        chip_line = Text.from_markup(f"[{dim}]toolsets[/]  " + chips)

    # ── One compact stat line ────────────────────────────────────────────
    stats = [
        f"[{accent}]{len(tools)}[/] [{dim}]tools[/]",
        f"[{accent}]{total_skills}[/] [{dim}]skills[/]",
        f"[{accent}]{n_providers}[/] [{dim}]providers[/]",
    ]
    if mcp_connected:
        stats.append(f"[{accent}]{mcp_connected}[/] [{dim}]MCP[/]")
    stats.append(f"[{dim}]/help[/]")
    stat_line = Align.center(Text.from_markup(f"[{dim}]  ·  [/]".join(stats)))

    # Gradient hairline rules (violet→sky) instead of a flat border color —
    # the bold-gradient-rice signature carried into the info card.
    _inner_w = max(8, min(shutil.get_terminal_size().columns, 72) - 8)
    def _grule():
        return Text.from_markup(rice.gradient_rule(_inner_w))

    body: list = [facts, _grule()]
    if chip_line is not None:
        body.append(chip_line)
        body.append(_grule())
    body.append(stat_line)
    notice_start = len(body)

    # Update / profile notices — minimal, only when they matter.
    try:
        behind = get_update_result(timeout=0.5)
        if behind:
            from jettstui.config import recommended_update_command, get_managed_update_command
            if behind > 0:
                _w = "commit" if behind == 1 else "commits"
                body.append(Text.from_markup(
                    f"[bold yellow]⚠ {behind} {_w} behind[/] [dim yellow]· run {recommended_update_command()}[/]"))
            else:
                _cmd = get_managed_update_command()
                body.append(Text.from_markup(
                    "[bold yellow]⚠ update available[/]" + (f" [dim yellow]· run {_cmd}[/]" if _cmd else "")))
    except Exception:
        pass

    try:
        from jettstui.profiles import get_active_profile_name
        _profile_name = get_active_profile_name()
        if _profile_name and _profile_name != "default":
            body.append(Text.from_markup(f"[{dim}]profile[/]  [{text}]{escape(_profile_name)}[/]"))
    except Exception:
        pass

    if _bskin and _bskin.name == "studio":
        from jettstui.studio import welcome_panel
        notices = body[notice_start:]
        if os.getenv("JETTSTUI_YOLO_MODE"):
            notices.append(Text("YOLO · approvals bypassed", style="bold red"))
        console.print(welcome_panel(
            skin=_bskin, width=console.width, model=model, provider=provider,
            cwd=cwd, tools=len(tools), skills=total_skills,
            context=context_length, session=session_id, notices=notices,
        ))
        return

    version_label = format_banner_version_label()
    release_info = get_latest_release_tag()
    if release_info:
        _tag, _url = release_info
        title_markup = f"[bold {title_color}][link={_url}]  {version_label}  [/link][/]"
    else:
        title_markup = f"[bold {title_color}]  {version_label}  [/]"

    _card_width = min(shutil.get_terminal_size().columns, 72)
    outer_panel = Panel(
        Group(*body),
        title=title_markup,
        title_align="center",
        border_style=border_color,
        box=box.ROUNDED,
        padding=(1, 3),
        width=_card_width,
    )

    console.print()
    term_width = shutil.get_terminal_size().columns
    # The gradient wordmark is the hero on a roomy terminal; the compact prism
    # emblem stands in when there isn't room for it.
    if term_width >= 52:
        _logo = _bskin.banner_logo if _bskin and getattr(_bskin, "banner_logo", "") else JETTSTUI_AGENT_LOGO
        console.print(Align.center(_logo, width=_card_width))
        # Gradient hairline + tagline tie the wordmark to the info card.
        console.print(Align.center(Text.from_markup(rice.gradient_rule(min(_card_width - 2, 52))), width=_card_width))
        console.print(Align.center(Text.from_markup(f"[{dim}]bring-your-own-key coding agent[/]"), width=_card_width))
        console.print()
    else:
        _hero = _bskin.banner_hero if _bskin and getattr(_bskin, "banner_hero", "") else JETTSTUI_CADUCEUS
        console.print(_hero)
        console.print()
    console.print(Align.center(outer_panel, width=_card_width))
