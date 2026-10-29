"""``jettstui bot`` CLI — create and manage Jetts Bots (named AI teammates).

State lives in ``$JETTSTUI_HOME/bots/`` (see :mod:`agent.bots`). Footprint
ladder rung 2: a CLI command + gateway RPCs, with zero model-tool schema cost.
"""

from __future__ import annotations

import argparse
import json
import sys

from agent import bots


def build_parser(parent_subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = parent_subparsers.add_parser(
        "bot",
        help="Manage Jetts Bots (named AI teammates)",
        description=(
            "A Jetts Bot is a named teammate with a job, its own memory and its own "
            "ongoing conversation. Bots share what they know about you (USER.md)."
        ),
    )
    sub = parser.add_subparsers(dest="bot_action")

    p_create = sub.add_parser("create", help="Create a bot")
    p_create.add_argument("name", help="Bot name, e.g. 'Sales Outbound'")
    p_create.add_argument("--role", required=True, help="The bot's job, in plain words")
    p_create.add_argument("--model", default=None, help="Model for this bot (default: profile model)")
    p_create.add_argument("--provider", default=None)

    p_list = sub.add_parser("list", aliases=["ls"], help="List bots")
    p_list.add_argument("--json", action="store_true")

    p_show = sub.add_parser("show", help="Show one bot")
    p_show.add_argument("bot", help="Bot id")

    p_rm = sub.add_parser("remove", aliases=["rm"], help="Archive a bot (memory is kept)")
    p_rm.add_argument("bot", help="Bot id")

    p_pc = sub.add_parser("computer", help="Show or set the VM the Bots use as their own computer")
    p_pc.add_argument("vm", nargs="?", help="VM/VPS name (see `jettstui computer-use vm list`)")
    p_pc.add_argument("--clear", action="store_true", help="Bots go back to having no computer")

    parser.set_defaults(func=bots_command)
    return parser


def bots_command(args: argparse.Namespace) -> int:
    action = getattr(args, "bot_action", None)
    try:
        if action == "create":
            bot = bots.create_bot(args.name, args.role, model=args.model, provider=args.provider)
            print(f"Created bot '{bot['name']}' (id: {bot['id']}). Open it from the Bots tab in the desktop app.")
            return 0
        if action in ("list", "ls"):
            rows = bots.list_bots()
            if args.json:
                print(json.dumps(rows, indent=2))
            elif not rows:
                print("No bots yet. Create one: jettstui bot create \"Name\" --role \"what it does\"")
            for bot in [] if args.json else rows:
                model = f"  [{bot['model']}]" if bot.get("model") else ""
                print(f"{bot['id']:<24} {bot['name']}{model}\n    {bot['role']}")
            return 0
        if action == "show":
            bot = bots.get_bot(args.bot)
            if bot is None:
                raise ValueError(f"no bot named {args.bot!r}")
            print(json.dumps(bot, indent=2))
            return 0
        if action == "computer":
            if args.clear or args.vm:
                bots.set_bot_computer(None if args.clear else args.vm)
            current = bots.bot_computer()
            print(f"Bots' computer: {current}" if current else "The Bots have no computer of their own; desktop work uses yours, with approval.")
            return 0
        if action in ("remove", "rm"):
            dest = bots.remove_bot(args.bot)
            print(f"Archived bot '{args.bot}' to {dest}")
            return 0
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print("usage: jettstui bot {create,list,show,remove,computer}", file=sys.stderr)
    return 1
