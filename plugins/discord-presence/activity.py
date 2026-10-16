"""Pure presence model: settings, runtime snapshot, and activity composition.

Nothing here touches the network or the clock — ``compose_activity`` turns
(settings, snapshot, now) into the exact ``SET_ACTIVITY`` payload, which keeps
privacy rules and Discord's field limits testable in isolation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Mapping, Optional, Tuple

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

PHASE_IDLE = "idle"
PHASE_THINKING = "thinking"
PHASE_TOOL = "tool"
PHASE_APPROVAL = "approval"

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
PRESETS: Dict[str, Dict[str, Any]] = {
    "pairing": {
        "label": "Pairing",
        "details": ("Pair programming with JettsTUI",),
        "state": ("{activity}", "{model}"),
    },
    "vibe_coding": {
        "label": "Vibe coding",
        "details": ("Vibe coding", "{project}"),
        "state": ("{activity}",),
    },
    "autonomous": {
        "label": "Autonomous",
        "details": ("Autonomous agent at work", "{project}"),
        "state": ("{activity}", "{tool_calls}"),
    },
    "minimal": {
        "label": "Minimal",
        "details": ("Using JettsTUI",),
        "state": ("{activity}",),
    },
}
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

    def with_(self, **changes: Any) -> "Snapshot":
        return replace(self, **changes)


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


def _variables(settings: PresenceSettings, snapshot: Snapshot) -> Dict[str, str]:
    calls = snapshot.tool_calls
    return {
        "activity": activity_text(settings, snapshot),
        "model": _model_label(snapshot.model) if settings.show_model else "",
        "project": snapshot.project.strip() if settings.show_project else "",
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
    details = render_template(settings.details, variables) if settings.details else _join_parts(preset["details"], variables)
    state = render_template(settings.state, variables) if settings.state else _join_parts(preset["state"], variables)

    activity: Dict[str, Any] = {"type": ACTIVITY_TYPES.get(settings.activity_type, 0), "instance": False}
    if fit_text(details):
        activity["details"] = fit_text(details)
    if fit_text(state):
        activity["state"] = fit_text(state)

    if settings.show_elapsed and snapshot.started_at:
        activity["timestamps"] = {"start": int(snapshot.started_at)}

    assets: Dict[str, str] = {}
    if settings.large_image:
        assets["large_image"] = settings.large_image
        large_text = fit_text(render_template(settings.large_text, variables))
        if large_text:
            assets["large_text"] = large_text
    if settings.small_image:
        assets["small_image"] = settings.small_image
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
