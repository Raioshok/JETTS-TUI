"""Compact, cell-aware terminal presentation for the Studio skin.

Rendering only: no network probes, configuration writes, or animation timers.
"""

from pathlib import Path

from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.cells import cell_len, set_cell_size


ACTIVITY_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")


def activity_line(label, *, width, now, elapsed=None, tokens="", reduce_motion=False):
    """One stable status row, measured in terminal cells, with an honest timer."""
    frame = "·" if reduce_motion else ACTIVITY_FRAMES[int(now / 0.12) % len(ACTIVITY_FRAMES)]
    label = " ".join(Text.from_ansi(label).plain.split()).removeprefix("· ")
    details = []
    if elapsed is not None:
        seconds = max(0, int(elapsed))
        details.append(f"{seconds // 60:02d}:{seconds % 60:02d}")
    if tokens:
        details.append(tokens)
    suffix = "  " + " · ".join(details) if details else ""
    prefix = f"  {frame} "
    # At small widths, prioritize the activity over accounting details.
    if cell_len(prefix + suffix) + 12 > width:
        suffix = ""
    available = max(0, width - cell_len(prefix + suffix) - 1)
    if cell_len(label) > available:
        label = (set_cell_size(label, available - 1) + "…") if available else ""
    result = prefix + label + suffix
    return set_cell_size(result, max(0, width - 1)).rstrip()


def welcome_panel(*, skin, width, model, provider, cwd, tools, skills,
                  context=None, session=None, notices=()):
    """Build a responsive launch card; dynamic values are always literal text."""
    width = max(1, min(width, 88))
    accent = skin.get_color("ui_accent")
    muted = skin.get_color("banner_dim")
    ink = skin.get_color("banner_text")
    compact = width < 54
    title = Text("Jetts-TUI", style=f"bold {ink}")
    title.append("  /  Studio", style=accent)

    facts = Table.grid(padding=(0, 2), expand=True)
    facts.add_column(style=muted, width=9, no_wrap=True)
    facts.add_column(style=ink, overflow="ellipsis", no_wrap=True, ratio=1)
    model_label = str(model)
    if provider:
        model_label += f" · {provider}"
    facts.add_row("Model", Text(model_label))
    try:
        relative = Path(cwd).relative_to(Path.home()).as_posix()
        workspace = "~" if relative == "." else f"~/{relative}"
    except (ValueError, OSError):
        workspace = str(cwd)
    facts.add_row("Workspace", Text(workspace))
    if context:
        facts.add_row("Context", Text(f"{context:,} tokens"))
    if session and not compact:
        facts.add_row("Session", Text(str(session)))

    capabilities = Text(f"{tools} tools  ·  {skills} skills", style=muted)
    shortcuts = Text()
    actions = [("/help", "commands"), ("/model", "switch model")]
    if not compact:
        actions.append(("/resume", "sessions"))
    for i, (command, label) in enumerate(actions):
        if i:
            shortcuts.append("   ", style=muted)
        shortcuts.append(command, style=accent)
        shortcuts.append(f" {label}", style=muted)

    content = Group(
        Text("Your workspace, ready to build.", style=muted),
        Text(""), facts, Text(""), capabilities, shortcuts, *notices,
    )
    return Panel(content, title=title, title_align="left", width=width,
                 box=box.ROUNDED, padding=(1, 1 if compact else 2),
                 border_style=skin.get_color("banner_border"))


def composer_hint(*, busy=False, mode="interrupt", width=80):
    """Explain what Enter actually does, without introducing new shortcuts."""
    if busy:
        action = {"queue": "queue a follow-up", "steer": "guide this run"}.get(
            mode, "redirect this run")
        return f"Enter to {action} · Ctrl+C to stop"
    if width < 54:
        return "Ask anything · /help"
    if width >= 82:
        return "Describe a task, ask a question, or / for commands · Shift+Tab mode"
    return "Describe a task, ask a question, or / for commands"
