"""Discord Rich Presence for JettsTUI.

Shows what the agent is doing (thinking, editing code, running commands,
waiting for approval) on the user's Discord profile. Opt-in twice over: the
plugin must be enabled, and ``discord_rpc.enabled`` must be true with a
Discord Application ID configured. Tool arguments, prompts and file paths
are never sent — only a friendly verb, and the model / project name when the
user allows it.
"""

from __future__ import annotations

import argparse
import shlex

from . import activity as act
from . import commands
from .ipc import DiscordIPCError
from .service import get_service

_HELP = """Usage: /rpc [status|on|off|preset <name>|refresh]

  status          Show connection state and what is being shared
  on | off        Turn Discord presence on or off
  preset <name>   Switch preset (""" + ", ".join(act.PRESETS) + """)
  refresh         Re-read config and resend the activity now

Set the Discord Application ID with: jettstui rpc setup <application-id>"""


# ----------------------------------------------------------------- hooks

def _on_session_start(session_id: str = "", model: str = "", platform: str = "", task_id: str = "", **_: object) -> None:
    get_service().session_started(session_id=session_id or "", model=model or "", platform=platform or "", task_id=task_id or "")


def _on_pre_llm_call(session_id: str = "", model: str = "", platform: str = "", task_id: str = "", **_: object) -> None:
    get_service().turn_started(session_id=session_id or "", model=model or "", platform=platform or "", task_id=task_id or "")


def _on_pre_tool_call(tool_name: str = "", session_id: str = "", tool_call_id: str = "", task_id: str = "", **_: object) -> None:
    get_service().tool_started(
        session_id=session_id or "", tool_call_id=tool_call_id or "", tool_name=tool_name, task_id=task_id or ""
    )


def _on_post_tool_call(tool_name: str = "", session_id: str = "", tool_call_id: str = "", task_id: str = "", **_: object) -> None:
    get_service().tool_finished(
        session_id=session_id or "", tool_call_id=tool_call_id or "", tool_name=tool_name, task_id=task_id or ""
    )


def _on_approval_request(session_id: str = "", session_key: str = "", **_: object) -> None:
    get_service().approval_requested(session_id=session_id or session_key or "")


def _on_approval_response(session_id: str = "", session_key: str = "", **_: object) -> None:
    get_service().approval_resolved(session_id=session_id or session_key or "")


def _on_turn_end(session_id: str = "", **_: object) -> None:
    # ``on_session_end`` fires at the end of every run_conversation() call,
    # i.e. once per turn — the agent is idle again.
    get_service().turn_finished(session_id=session_id or "")


def _on_session_reset(session_id: str = "", **_: object) -> None:
    get_service().session_reset(session_id=session_id or "")


# ----------------------------------------------------------- slash command

def _handle_slash(raw_args: str) -> str:
    try:
        parts = shlex.split(raw_args or "")
    except ValueError:
        parts = (raw_args or "").split()
    sub = parts[0].lower() if parts else "status"
    service = get_service()
    try:
        if sub in {"status", ""}:
            return commands.format_status(service.status())
        if sub in {"on", "enable"}:
            status = commands.set_enabled(True)
            if not status["configured"]:
                return "Discord presence enabled. Set your Application ID next: jettstui rpc setup <application-id>"
            return "Discord presence enabled."
        if sub in {"off", "disable"}:
            commands.set_enabled(False)
            return "Discord presence disabled; your Discord activity has been cleared."
        if sub == "preset":
            if len(parts) < 2:
                current = service.settings().preset
                return "Presets: " + ", ".join(f"{name}{' (active)' if name == current else ''}" for name in act.PRESETS)
            return f"Preset set to {commands.set_preset(parts[1])}."
        if sub == "refresh":
            service.refresh()
            return "Presence refreshed."
    except (ValueError, OSError) as exc:
        return f"Error: {exc}"
    return _HELP


# ------------------------------------------------------------- CLI command

def _setup_cli(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="rpc_action")
    sub.add_parser("status", help="Show configuration and Discord connection")
    setup = sub.add_parser("setup", help="Validate and store your Discord Application ID, then enable presence")
    setup.add_argument("client_id", help="Application ID from https://discord.com/developers/applications")
    sub.add_parser("on", help="Enable Discord presence")
    sub.add_parser("off", help="Disable Discord presence and clear the activity")
    preset = sub.add_parser("preset", help="List presets or switch to one")
    preset.add_argument("name", nargs="?", choices=sorted(act.PRESETS))
    test = sub.add_parser("test", help="Show the preview card on Discord for a few seconds")
    test.add_argument("--seconds", type=float, default=15.0)


def _run_cli(args: argparse.Namespace) -> int:
    action = getattr(args, "rpc_action", None) or "status"
    service = get_service()
    try:
        if action == "status":
            settings = service.settings(fresh=True)
            user, error = commands.probe(settings.client_id) if settings.configured else (None, "")
            print(commands.format_status(service.status(), user=user or {}, error=error))
            return 0
        if action == "setup":
            app = commands.set_client_id(args.client_id)
            commands.set_enabled(True)
            print(f"✓ Using Discord application “{app['name'] or app['id']}” ({app['id']}). Presence enabled.")
            user, _ = commands.probe(app["id"])
            print(f"✓ Discord is running — signed in as {user.get('global_name') or user.get('username')}." if user
                  else "Discord is not running right now; presence starts automatically when it is.")
            return 0
        if action == "on":
            status = commands.set_enabled(True)
            print("✓ Discord presence enabled." if status["configured"]
                  else "✓ Enabled. Set your Application ID next: jettstui rpc setup <application-id>")
            return 0
        if action == "off":
            commands.set_enabled(False)
            print("✓ Discord presence disabled.")
            return 0
        if action == "preset":
            if not args.name:
                current = service.settings(fresh=True).preset
                for name, spec in act.PRESETS.items():
                    print(f"  {'●' if name == current else '○'} {name:<12} {spec['label']}")
                return 0
            print(f"✓ Preset set to {commands.set_preset(args.name)}.")
            return 0
        if action == "test":
            result = commands.send_test(args.seconds)
            activity = result["activity"] or {}
            print(f"✓ Showing on Discord for {args.seconds:g}s: {activity.get('details', '')} — {activity.get('state', '')}")
            return 0
    except (ValueError, OSError, DiscordIPCError) as exc:
        print(f"✗ {exc}")
        return 1
    return 0


def register(ctx) -> None:
    ctx.register_hook("on_session_start", _on_session_start)
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
    ctx.register_hook("pre_tool_call", _on_pre_tool_call)
    ctx.register_hook("post_tool_call", _on_post_tool_call)
    ctx.register_hook("pre_approval_request", _on_approval_request)
    ctx.register_hook("post_approval_response", _on_approval_response)
    ctx.register_hook("on_session_end", _on_turn_end)
    ctx.register_hook("on_session_reset", _on_session_reset)
    ctx.register_hook("on_session_finalize", _on_session_reset)
    ctx.register_command(
        "rpc",
        handler=_handle_slash,
        description="Discord Rich Presence: status, on/off, presets",
        args_hint="[status|on|off|preset <name>|refresh]",
    )
    ctx.register_cli_command(
        "rpc",
        help="Discord Rich Presence",
        setup_fn=_setup_cli,
        handler_fn=_run_cli,
        description="Show what JettsTUI is doing on your Discord profile.",
    )
