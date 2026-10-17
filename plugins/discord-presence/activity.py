"""Pure presence model: settings, runtime snapshot, and activity composition.

Nothing here touches the network or the clock — ``compose_activity`` turns
(settings, snapshot, now) into the exact ``SET_ACTIVITY`` payload, which keeps
privacy rules and Discord's field limits testable in isolation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

CONFIG_SECTION = "discord_rpc"

DEFAULT_LARGE_IMAGE = "https://raw.githubusercontent.com/Raioshok/JETTS-TUI/main/apps/desktop/assets/icon.png"
DEFAULT_BUTTONS: Tuple[Tuple[str, str], ...] = (("View on GitHub", "https://github.com/Raioshok/JETTS-TUI"),)

# Discord's documented field limits for rich presence.
MIN_TEXT = 2
MAX_TEXT = 128
MAX_BUTTONS = 2
MAX_BUTTON_LABEL = 32
MAX_BUTTON_URL = 512

ACTIVITY_TYPES: Dict[str, int] = {"playing": 0, "listening": 2, "watching": 3, "competing": 5}
# Which line Discord shows under the user's name in member lists.
STATUS_DISPLAY_TYPES: Dict[str, int] = {"name": 0, "state": 1, "details": 2}

PHASE_IDLE = "idle"
PHASE_THINKING = "thinking"
PHASE_TOOL = "tool"
PHASE_APPROVAL = "approval"

# When several sessions are live, the card follows the one that most needs
# the user's attention, then the most recently active.
_PHASE_PRIORITY = {PHASE_APPROVAL: 3, PHASE_TOOL: 2, PHASE_THINKING: 1, PHASE_IDLE: 0}

# Corner badge per phase (Twemoji, CC-BY 4.0), used when no small image is set.
_TWEMOJI = "https://cdn.jsdelivr.net/gh/jdecked/twemoji@15.1.0/assets/72x72/{}.png"
PHASE_BADGES: Dict[str, str] = {
    PHASE_THINKING: _TWEMOJI.format("1f9e0"),
    PHASE_TOOL: _TWEMOJI.format("26a1"),
    PHASE_APPROVAL: _TWEMOJI.format("270b"),
    PHASE_IDLE: _TWEMOJI.format("1f4a4"),
}

# Friendly, argument-free descriptions. Tool arguments never leave the machine.
_TOOL_VERBS: Tuple[Tuple[str, str], ...] = (
    ("terminal", "Running commands"),
    ("process", "Running commands"),
    ("execute_code", "Running code"),
    ("read_file", "Reading code"),
    ("search_files", "Searching the codebase"),
    ("write_file", "Writing code"),
    ("patch", "Editing code"),
    ("web_search", "Researching the web"),
    ("web_extract", "Reading the web"),
    ("browser_", "Browsing the web"),
    ("delegate_task", "Coordinating subagents"),
    ("vision_", "Looking at images"),
    ("image_gen", "Generating images"),
    ("memory", "Updating memory"),
    ("skill", "Using skills"),
    ("todo", "Planning"),
    ("cronjob", "Scheduling jobs"),
    ("kanban_", "Working the board"),
    ("mcp_", "Using integrations"),
)

_PHASE_TEXT = {
    PHASE_IDLE: "Idle",
    PHASE_THINKING: "Thinking",
    PHASE_APPROVAL: "Waiting for approval",
}

# Each preset is (details parts, state parts). Parts are joined with " · "
# after rendering, and any part that renders empty (a hidden field) is dropped.
# ``multi_details`` replaces ``details`` while more than one project is live;
# the state line then names the project the activity belongs to.
PRESETS: Dict[str, Dict[str, Any]] = {
    "pairing": {
        "label": "Pairing",
        "details": ("Pair programming with JettsTUI",),
        "multi_details": ("Pairing across {project_count}",),
        "state": ("{activity}", "{model}"),
    },
    "vibe_coding": {
        "label": "Vibe coding",
        "details": ("Vibe coding", "{project}"),
        "multi_details": ("Vibe coding across {project_count}",),
        "state": ("{activity}",),
    },
    "autonomous": {
        "label": "Autonomous",
        "details": ("Autonomous agent at work", "{project}"),
        "multi_details": ("Agents at work in {project_count}",),
        "state": ("{activity}", "{tool_calls}"),
    },
    "minimal": {
        "label": "Minimal",
        "details": ("Using JettsTUI",),
        "multi_details": ("Working in {project_count}",),
        "state": ("{activity}",),
    },
}
_MULTI_STATE = ("{activity}", "{project}")
DEFAULT_PRESET = "pairing"
# Names shipped by the first version of this feature.
PRESET_ALIASES = {"fine_tuning": "autonomous", "idle": "minimal"}

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _as_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


# The first version of this feature shipped a placeholder ID that Discord
# answers with "Unknown Application"; treat it (if saved in a user's config)
# as unset so status says "not configured" instead of failing forever.
_PLACEHOLDER_CLIENT_IDS = frozenset({"1343714589234567890"})


def normalize_client_id(value: Any) -> str:
    """Return a Discord snowflake string, or "" when the value is not one."""
    text = str(value).strip() if value is not None else ""
    if text in _PLACEHOLDER_CLIENT_IDS:
        return ""
    return text if re.fullmatch(r"\d{17,20}", text) else ""


def resolve_preset(name: str) -> str:
    name = PRESET_ALIASES.get(name, name)
    return name if name in PRESETS else DEFAULT_PRESET


def valid_button(label: Any, url: Any) -> Optional[Tuple[str, str]]:
    label = _as_text(label)
    url = _as_text(url)
    if not label or not url or len(url) > MAX_BUTTON_URL or not url.lower().startswith("https://"):
        return None
    return label[:MAX_BUTTON_LABEL], url


@dataclass(frozen=True)
class PresenceSettings:
    enabled: bool = False
    client_id: str = ""
    preset: str = DEFAULT_PRESET
    activity_type: str = "playing"
    show_model: bool = True
    show_project: bool = True
    show_tool_activity: bool = True
    show_elapsed: bool = True
    phase_badges: bool = True
    status_display: str = "details"
    idle_timeout_minutes: int = 15
    details: str = ""
    state: str = ""
    large_image: str = DEFAULT_LARGE_IMAGE
    large_text: str = "JettsTUI"
    small_image: str = ""
    small_text: str = ""
    buttons: Tuple[Tuple[str, str], ...] = field(default=DEFAULT_BUTTONS)

    @property
    def configured(self) -> bool:
        return bool(self.client_id)

    @classmethod
    def from_config(cls, config: Optional[Mapping[str, Any]]) -> "PresenceSettings":
        section = (config or {}).get(CONFIG_SECTION)
        if not isinstance(section, Mapping):
            return cls()
        base = cls()

        buttons: Tuple[Tuple[str, str], ...] = base.buttons
        raw_buttons = section.get("buttons")
        if isinstance(raw_buttons, list):
            parsed = []
            for item in raw_buttons:
                if isinstance(item, Mapping):
                    button = valid_button(item.get("label"), item.get("url"))
                    if button:
                        parsed.append(button)
            buttons = tuple(parsed[:MAX_BUTTONS])

        try:
            idle = int(section.get("idle_timeout_minutes", base.idle_timeout_minutes))
        except (TypeError, ValueError):
            idle = base.idle_timeout_minutes

        activity_type = _as_text(section.get("activity_type")).lower() or base.activity_type
        if activity_type not in ACTIVITY_TYPES:
            activity_type = base.activity_type

        status_display = _as_text(section.get("status_display")).lower() or base.status_display
        if status_display not in STATUS_DISPLAY_TYPES:
            status_display = base.status_display

        def text(key: str, default: str) -> str:
            return _as_text(section[key]) if key in section else default

        return cls(
            enabled=_as_bool(section.get("enabled"), base.enabled),
            client_id=normalize_client_id(section.get("client_id")),
            preset=resolve_preset(_as_text(section.get("preset")) or base.preset),
            activity_type=activity_type,
            show_model=_as_bool(section.get("show_model"), base.show_model),
            show_project=_as_bool(section.get("show_project"), base.show_project),
            show_tool_activity=_as_bool(section.get("show_tool_activity"), base.show_tool_activity),
            show_elapsed=_as_bool(section.get("show_elapsed"), base.show_elapsed),
            phase_badges=_as_bool(section.get("phase_badges"), base.phase_badges),
            status_display=status_display,
            idle_timeout_minutes=max(0, idle),
            details=text("details", base.details),
            state=text("state", base.state),
            large_image=text("large_image", base.large_image),
            large_text=text("large_text", base.large_text),
            small_image=text("small_image", base.small_image),
            small_text=text("small_text", base.small_text),
            buttons=buttons,
        )

    def to_public(self) -> Dict[str, Any]:
        """JSON shape for the CLI/desktop (config keys, not internals)."""
        return {
            "enabled": self.enabled,
            "client_id": self.client_id,
            "preset": self.preset,
            "activity_type": self.activity_type,
            "show_model": self.show_model,
            "show_project": self.show_project,
            "show_tool_activity": self.show_tool_activity,
            "show_elapsed": self.show_elapsed,
            "phase_badges": self.phase_badges,
            "status_display": self.status_display,
            "idle_timeout_minutes": self.idle_timeout_minutes,
            "details": self.details,
            "state": self.state,
            "large_image": self.large_image,
            "large_text": self.large_text,
            "small_image": self.small_image,
            "small_text": self.small_text,
            "buttons": [{"label": label, "url": url} for label, url in self.buttons],
        }


@dataclass(frozen=True)
class Snapshot:
    """What the agent is doing right now, as far as presence cares."""

    phase: str = PHASE_IDLE
    tool: str = ""
    model: str = ""
    project: str = ""
    started_at: Optional[float] = None
    last_active_at: float = 0.0
    tool_calls: int = 0
    # Every live project, the focused one first. Empty means just ``project``.
    projects: Tuple[str, ...] = ()

    def with_(self, **changes: Any) -> "Snapshot":
        return replace(self, **changes)

    @property
    def project_names(self) -> Tuple[str, ...]:
        if self.projects:
            return self.projects
        return (self.project,) if self.project else ()


def aggregate(sessions: Iterable[Snapshot]) -> Snapshot:
    """Fold every live session into one card-worthy snapshot.

    The focus is the session that most needs attention (approval > tool >
    thinking > idle), ties broken by recency. Elapsed time starts at the
    earliest session, and tool calls add up.
    """
    live = list(sessions)
    if not live:
        return Snapshot()
    focus = max(live, key=lambda s: (_PHASE_PRIORITY.get(s.phase, 0), s.last_active_at))
    names: List[str] = []
    for session in [focus, *sorted(live, key=lambda s: s.last_active_at, reverse=True)]:
        if session.project and session.project not in names:
            names.append(session.project)
    starts = [s.started_at for s in live if s.started_at]
    return focus.with_(
        projects=tuple(names),
        started_at=min(starts) if starts else None,
        last_active_at=max(s.last_active_at for s in live),
        tool_calls=sum(s.tool_calls for s in live),
    )


def describe_tool(tool_name: str) -> str:
    name = (tool_name or "").strip().lower()
    for prefix, verb in _TOOL_VERBS:
        if name == prefix or name.startswith(prefix):
            return verb
    return "Using tools"


def activity_text(settings: PresenceSettings, snapshot: Snapshot) -> str:
    if snapshot.phase == PHASE_TOOL:
        return describe_tool(snapshot.tool) if settings.show_tool_activity else "Working"
    if snapshot.phase == PHASE_THINKING and not settings.show_tool_activity:
        return "Working"
    return _PHASE_TEXT.get(snapshot.phase, "Idle")


def _model_label(model: str) -> str:
    # "anthropic/claude-sonnet-4" → "claude-sonnet-4": the vendor prefix is noise.
    return (model or "").strip().rsplit("/", 1)[-1]


def _project_list(names: Tuple[str, ...], limit: int = 3) -> str:
    shown = ", ".join(names[:limit])
    return f"{shown} +{len(names) - limit}" if len(names) > limit else shown


def _variables(settings: PresenceSettings, snapshot: Snapshot) -> Dict[str, str]:
    calls = snapshot.tool_calls
    names = snapshot.project_names
    count = len(names)
    # A count reveals nothing identifying, so it shows even with names hidden.
    project_count = f"{count} project{'s' if count != 1 else ''}" if count else ""
    project = snapshot.project.strip() if settings.show_project else ""
    return {
        "activity": activity_text(settings, snapshot),
        "model": _model_label(snapshot.model) if settings.show_model else "",
        "project": project,
        "projects": _project_list(names) if settings.show_project else "",
        "project_count": project_count,
        "workspace": project_count if count > 1 else project,
        "tool_calls": (f"{calls} tool call{'s' if calls != 1 else ''}" if calls and settings.show_tool_activity else ""),
    }


def render_template(template: str, variables: Mapping[str, str]) -> str:
    """Fill ``{name}`` placeholders; unknown names render empty."""
    rendered = _PLACEHOLDER.sub(lambda m: variables.get(m.group(1), ""), template)
    # Hidden fields leave dangling separators ("Coding · ") — tidy them.
    rendered = re.sub(r"\s*(?:[·•|—-]\s*)+$", "", rendered)
    rendered = re.sub(r"^(?:\s*[·•|—-])+\s*", "", rendered)
    rendered = re.sub(r"\(\s*\)", "", rendered)
    return re.sub(r"\s{2,}", " ", rendered).strip()


def _join_parts(parts: Tuple[str, ...], variables: Mapping[str, str]) -> str:
    rendered = [render_template(part, variables) for part in parts]
    return " · ".join(part for part in rendered if part)


def fit_text(value: str) -> Optional[str]:
    """Clamp to Discord's 2–128 character window; too-short text is dropped."""
    value = (value or "").strip()
    if len(value) < MIN_TEXT:
        return None
    if len(value) > MAX_TEXT:
        value = value[: MAX_TEXT - 1].rstrip() + "…"
    return value


def is_idle_expired(settings: PresenceSettings, snapshot: Snapshot, now: float) -> bool:
    if snapshot.phase != PHASE_IDLE or settings.idle_timeout_minutes <= 0:
        return False
    if not snapshot.last_active_at:
        return True
    return now - snapshot.last_active_at >= settings.idle_timeout_minutes * 60


def compose_activity(settings: PresenceSettings, snapshot: Snapshot, now: float) -> Optional[Dict[str, Any]]:
    """Build the ``activity`` object for SET_ACTIVITY, or ``None`` to clear it."""
    if is_idle_expired(settings, snapshot, now):
        return None

    preset = PRESETS[resolve_preset(settings.preset)]
    variables = _variables(settings, snapshot)
    multi = len(snapshot.project_names) > 1
    details_parts = preset["multi_details"] if multi else preset["details"]
    state_parts = _MULTI_STATE if multi else preset["state"]
    details = render_template(settings.details, variables) if settings.details else _join_parts(details_parts, variables)
    state = render_template(settings.state, variables) if settings.state else _join_parts(state_parts, variables)

    activity: Dict[str, Any] = {"type": ACTIVITY_TYPES.get(settings.activity_type, 0), "instance": False}
    status_display = STATUS_DISPLAY_TYPES.get(settings.status_display, 0)
    if status_display:
        activity["status_display_type"] = status_display
    if fit_text(details):
        activity["details"] = fit_text(details)
    if fit_text(state):
        activity["state"] = fit_text(state)

    if settings.show_elapsed and snapshot.started_at:
        activity["timestamps"] = {"start": int(snapshot.started_at)}

    assets: Dict[str, str] = {}
    if settings.large_image:
        assets["large_image"] = settings.large_image
        large_text = render_template(settings.large_text, variables)
        if multi and variables["projects"] and settings.large_text == PresenceSettings.large_text:
            # Hovering the art lists the projects instead of crowding the text lines.
            large_text = f"{large_text} · {variables['projects']}"
        large_text = fit_text(large_text)
        if large_text:
            assets["large_text"] = large_text
    small_image = settings.small_image or (PHASE_BADGES.get(snapshot.phase, "") if settings.phase_badges else "")
    if small_image:
        assets["small_image"] = small_image
        small_text = fit_text(render_template(settings.small_text, variables) or variables["activity"])
        if small_text:
            assets["small_text"] = small_text
    if assets:
        activity["assets"] = assets

    buttons: List[Dict[str, str]] = []
    for label, url in settings.buttons[:MAX_BUTTONS]:
        button = valid_button(label, url)
        if button:
            buttons.append({"label": button[0], "url": button[1]})
    if buttons:
        activity["buttons"] = buttons
    return activity
