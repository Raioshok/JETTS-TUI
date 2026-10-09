"""Render the real Studio components without credentials or model calls.

Run: python scripts/preview_studio.py --output <preview.svg>
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rich.console import Console
from rich.terminal_theme import TerminalTheme
from rich.text import Text

from jettstui.skin_engine import load_skin
from jettstui.studio import activity_line, composer_hint, welcome_panel


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--width", type=int, default=88)
    parser.add_argument("--light", action="store_true")
    args = parser.parse_args()
    skin = load_skin("studio")
    if args.light:
        skin.colors.update(skin.light_colors)
    console = Console(record=True, width=max(20, args.width), color_system="truecolor")
    console.print(welcome_panel(
        skin=skin, width=console.width, model="deepseek-v4-flash", provider="nvidia",
        cwd=str(Path.cwd()), tools=24, skills=8, context=128000, session="design-preview",
    ))
    console.print()
    console.print(Text("  You", style=f"bold {skin.colors['banner_title']}"))
    console.print(Text("  Find the slow query and explain how to improve it."))
    console.print()
    console.print(Text(activity_line(
        "Reading src/database/queries.py", width=console.width, now=0.6,
        elapsed=12, tokens="842 tokens",
    ), style=skin.colors["ui_accent"]))
    console.print(Text("─" * (console.width - 1), style=skin.colors["input_rule"]))
    console.print(Text("❯ " + composer_hint(width=console.width), style=skin.colors["banner_dim"]))
    console.print()
    console.print(Text("  DESIGN PREVIEW · example session data", style=skin.colors["banner_dim"]))
    rgb = lambda value: tuple(int(value[i:i+2], 16) for i in (1, 3, 5))
    theme = TerminalTheme(rgb(skin.colors["background"]), rgb(skin.colors["banner_text"]),
                          [(0, 0, 0)] * 8)
    console.save_svg(str(args.output), title="JettsTUI / Studio", theme=theme)


if __name__ == "__main__":
    main()
