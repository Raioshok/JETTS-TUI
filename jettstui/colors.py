"""Shared ANSI color utilities for JettsTUI CLI modules."""

import os
import sys


def should_use_color() -> bool:
    """Return True when colored output is appropriate.

    Respects the NO_COLOR environment variable (https://no-color.org/)
    and TERM=dumb, in addition to the existing TTY check.
    """
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    if not sys.stdout.isatty():
        return False
    return True


def _supports_truecolor() -> bool:
    """True when the terminal advertises 24-bit color support."""
    if os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit"):
        return True
    if os.environ.get("WT_SESSION"):  # Windows Terminal
        return True
    return os.environ.get("TERM_PROGRAM", "") in ("vscode", "iTerm.app", "WezTerm")


class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    # Prism violet accent (desktop/dashboard #9583FF); nearest 256-color
    # violet when the terminal doesn't advertise truecolor.
    BRAND = "\033[38;2;149;131;255m" if _supports_truecolor() else "\033[38;5;141m"


def color(text: str, *codes) -> str:
    """Apply color codes to text (only when color output is appropriate)."""
    if not should_use_color():
        return text
    return "".join(codes) + text + Colors.RESET
