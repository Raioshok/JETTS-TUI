"""Bold-gradient-rice primitives — the shared visual layer for FreeIDE's TUI.

One place for the violet→sky gradient and the powerline segment language so
every surface (banner, status bar, context meter, input rule, pickers) reads as
one deliberate, heavily-riced scheme instead of scattered ad-hoc colors.

Everything degrades: `gradient_*` fall back to a flat accent when truecolor is
unavailable, and the powerline separators are overridable per-skin (and via
``FREEIDE_POWERLINE=0``) for fonts without the nerd-font glyphs.
"""

from __future__ import annotations

import os
from typing import List, Sequence, Tuple


# =============================================================================
# The signature gradient — Catppuccin mauve → lavender → blue → sky.
# The whole "bold gradient rice" identity flows from this single ramp.
# =============================================================================

VIOLET_SKY: Tuple[str, ...] = (
    "#cba6f7",  # mauve
    "#c0a9f8",
    "#b4befe",  # lavender
    "#a6b8fc",
    "#89b4fa",  # blue
    "#89dceb",  # sky
)


# =============================================================================
# Powerline glyphs (nerd-font). Overridable per skin / via env for plain fonts.
# =============================================================================

# Solid triangles (U+E0B0 / U+E0B2) and thin dividers (U+E0B1 / U+E0B3).
PL_RIGHT = ""
PL_RIGHT_THIN = ""
PL_LEFT = ""
PL_LEFT_THIN = ""

# Plain-font fallbacks: half-blocks read as slanted segment edges without a
# nerd font. Chosen so the segmented look survives even on tofu terminals.
_PL_RIGHT_FALLBACK = "▶"  # ▶
_PL_LEFT_FALLBACK = "◀"   # ◀


def powerline_enabled() -> bool:
    """False when the user opts out of nerd-font powerline glyphs."""
    return os.environ.get("FREEIDE_POWERLINE", "1").strip().lower() not in {"0", "false", "no", "off"}


def pl_right() -> str:
    return PL_RIGHT if powerline_enabled() else _PL_RIGHT_FALLBACK


def pl_left() -> str:
    return PL_LEFT if powerline_enabled() else _PL_LEFT_FALLBACK


# =============================================================================
# Truecolor gradient math
# =============================================================================

def _clamp8(v: float) -> int:
    return max(0, min(255, int(round(v))))


def _hex_to_rgb(h: str) -> Tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(rgb: Sequence[float]) -> str:
    return "#{:02x}{:02x}{:02x}".format(_clamp8(rgb[0]), _clamp8(rgb[1]), _clamp8(rgb[2]))


def gradient_at(t: float, stops: Sequence[str] = VIOLET_SKY) -> str:
    """Return the hex color at position ``t`` in [0, 1] along ``stops``."""
    stops = list(stops) or list(VIOLET_SKY)
    if len(stops) == 1:
        return stops[0]
    t = max(0.0, min(1.0, t))
    scaled = t * (len(stops) - 1)
    i = int(scaled)
    if i >= len(stops) - 1:
        return stops[-1]
    frac = scaled - i
    a = _hex_to_rgb(stops[i])
    b = _hex_to_rgb(stops[i + 1])
    return _rgb_to_hex([a[k] + (b[k] - a[k]) * frac for k in range(3)])


def gradient_spans(n: int, stops: Sequence[str] = VIOLET_SKY) -> List[str]:
    """Return ``n`` hex colors evenly sampled across ``stops``."""
    if n <= 0:
        return []
    if n == 1:
        return [gradient_at(0.5, stops)]
    return [gradient_at(i / (n - 1), stops) for i in range(n)]


# =============================================================================
# Rich-markup renderers (banner, help, pickers rendered through rich)
# =============================================================================

def gradient_markup(text: str, stops: Sequence[str] = VIOLET_SKY, *, bold: bool = False) -> str:
    """Per-character Rich markup gradient. Spaces pass through uncolored."""
    chars = list(text)
    colored = [c for c in chars if not c.isspace()]
    if not colored:
        return text
    ramp = gradient_spans(len(colored), stops)
    out: List[str] = []
    ci = 0
    b = "bold " if bold else ""
    for c in chars:
        if c.isspace():
            out.append(c)
        else:
            out.append(f"[{b}{ramp[ci]}]{c}[/]")
            ci += 1
    return "".join(out)


def gradient_rule(width: int, stops: Sequence[str] = VIOLET_SKY, char: str = "─") -> str:
    """A horizontal rule that fades across ``stops`` — Rich markup."""
    width = max(1, width)
    ramp = gradient_spans(width, stops)
    return "".join(f"[{ramp[i]}]{char}[/]" for i in range(width))


# =============================================================================
# prompt_toolkit fragment renderers (input rule, live surfaces)
# =============================================================================

def gradient_fragments(text: str, stops: Sequence[str] = VIOLET_SKY, *, bold: bool = False):
    """Per-character (style, char) fragments with a truecolor gradient fg."""
    chars = list(text)
    colored = [c for c in chars if not c.isspace()]
    ramp = gradient_spans(len(colored), stops) if colored else []
    frags = []
    ci = 0
    suffix = " bold" if bold else ""
    for c in chars:
        if c.isspace():
            frags.append(("", c))
        else:
            frags.append((f"{ramp[ci]}{suffix}", c))
            ci += 1
    return frags


def gradient_rule_fragments(width: int, stops: Sequence[str] = VIOLET_SKY, char: str = "─"):
    """A gradient horizontal rule as prompt_toolkit fragments."""
    width = max(1, width)
    ramp = gradient_spans(width, stops)
    return [(ramp[i], char) for i in range(width)]


def powerline_segments(segments: Sequence[Tuple[str, str, str]], *, sep: str = "") -> List[Tuple[str, str]]:
    """Build powerline status fragments from ``(fg, bg, text)`` segments.

    Each segment renders as ``fg on bg`` and is joined to the next by a
    separator glyph colored ``fg=this.bg on next.bg`` so the segments appear to
    slant into each other. A trailing separator fades the last segment into the
    terminal background.
    """
    sep = sep or pl_right()
    frags: List[Tuple[str, str]] = []
    n = len(segments)
    for i, (fg, bg, text) in enumerate(segments):
        frags.append((f"{fg} bg:{bg} bold", f" {text} "))
        next_bg = segments[i + 1][1] if i + 1 < n else None
        if next_bg is not None:
            frags.append((f"{bg} bg:{next_bg}", sep))
        else:
            # Fade the last segment into the terminal default background.
            frags.append((f"{bg}", sep))
    return frags
