"""``freeide brain`` subcommand parser."""

from __future__ import annotations

from typing import Callable


def build_brain_parser(subparsers, *, cmd_brain: Callable) -> None:
    parser = subparsers.add_parser(
        "brain",
        help="Create and maintain an Obsidian project brain",
        description="Scaffold a plugin-light Obsidian vault and maintain it incrementally.",
    )
    actions = parser.add_subparsers(dest="brain_action")
    init = actions.add_parser("init", help="Create or safely upgrade the vault")
    init.add_argument("vault", nargs="?", help="Vault path (default: config or ~/Documents/Jetts-TUI Brain)")
    init.add_argument("--project", help="Project to register (default: current directory)")
    status = actions.add_parser("status", help="Show vault health and capture counts")
    status.add_argument("--vault")
    doctor = actions.add_parser("doctor", help="Check structure and unresolved wikilinks")
    doctor.add_argument("--vault")
    capture = actions.add_parser("capture", help="Append a fast capture to the inbox")
    capture.add_argument("text", nargs="+")
    capture.add_argument("--vault")
    prompt = actions.add_parser("prompt", help="Print the agent prompt for scripted sync/review")
    prompt.add_argument("mode", choices=("sync", "improve"))
    prompt.add_argument("--vault")
    prompt.add_argument("--project")
    open_cmd = actions.add_parser("open", help="Open Dashboard.md through the official Obsidian CLI")
    open_cmd.add_argument("--vault")
    parser.set_defaults(func=cmd_brain)
