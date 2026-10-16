"""``jettstui rpc`` subcommand parser and handler.

Manages Discord Rich Presence (RPC) configuration, diagnostics, and testing.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import platform
import sys
import time
from typing import Callable, Optional

from jettstui.discord_rpc import (
    DEFAULT_CLIENT_ID,
    PRESETS,
    DiscordIPCClient,
    DiscordRPCManager,
    find_active_ipc_pipe,
    get_rpc_manager,
    init_rpc_manager,
    render_discord_card,
)


def build_rpc_parser(subparsers, *, cmd_rpc: Callable) -> None:
    """Attach the ``rpc`` subcommand to ``subparsers``."""
    rpc_parser = subparsers.add_parser(
        "rpc",
        help="Discord Rich Presence (RPC) management and diagnostics",
        description="Showcase JettsTUI activity on your Discord profile via Rich Presence.",
    )

    sub = rpc_parser.add_subparsers(dest="rpc_action", metavar="ACTION")

    # status
    p_status = sub.add_parser("status", help="Show Discord connection and preview profile card")
    p_status.add_argument("--json", action="store_true", help="Output raw JSON data")

    # test
    p_test = sub.add_parser("test", help="Push a test Rich Presence activity to your Discord client")
    p_test.add_argument("--preset", choices=list(PRESETS.keys()), default="pairing", help="Preset to test")
    p_test.add_argument("--details", type=str, help="Custom details line")
    p_test.add_argument("--state", type=str, help="Custom state line")
    p_test.add_argument("--duration", type=int, default=15, help="Duration to keep presence active (seconds, 0=forever)")

    # on / enable
    sub.add_parser("on", help="Enable Discord Rich Presence in config.yaml")
    sub.add_parser("enable", help="Alias for on")

    # off / disable
    sub.add_parser("off", help="Disable Discord Rich Presence in config.yaml")
    sub.add_parser("disable", help="Alias for off")

    # preset
    p_preset = sub.add_parser("preset", help="Select active activity preset")
    p_preset.add_argument("name", choices=list(PRESETS.keys()), help="Preset name")

    # set
    p_set = sub.add_parser("set", help="Set custom details or state format in config")
    p_set.add_argument("--client-id", type=str, help="Discord Application ID")
    p_set.add_argument("--details", type=str, help="Custom details template")
    p_set.add_argument("--state", type=str, help="Custom state template")

    # daemon
    p_daemon = sub.add_parser("daemon", help="Run standalone Discord RPC daemon in foreground")
    p_daemon.add_argument("--preset", choices=list(PRESETS.keys()), default="pairing", help="Preset to use")

    rpc_parser.set_defaults(func=cmd_rpc)


def cmd_rpc(args: argparse.Namespace) -> int:
    """Execute ``jettstui rpc`` subcommand."""
    action = getattr(args, "rpc_action", None) or "status"

    from jettstui.config import load_config
    from jettstui.config_edit import save_config_value

    cfg = load_config()
    rpc_cfg = cfg.get("discord_rpc", {})

    try:
        from rich.console import Console
        console = Console()
    except ImportError:
        console = None

    if action in ("status", None):
        client_id = rpc_cfg.get("client_id") or DEFAULT_CLIENT_ID
        preset_name = rpc_cfg.get("preset", "pairing")
        is_enabled = rpc_cfg.get("enabled", False)

        pipe = find_active_ipc_pipe()

        mgr = DiscordRPCManager(
            client_id=client_id,
            preset=preset_name,
            buttons=rpc_cfg.get("buttons"),
            large_image=rpc_cfg.get("large_image"),
            large_text=rpc_cfg.get("large_text"),
            small_image=rpc_cfg.get("small_image"),
            small_text=rpc_cfg.get("small_text"),
            enabled=is_enabled,
        )

        presence = mgr.build_current_presence()

        if getattr(args, "json", False):
            import json
            data = {
                "enabled": is_enabled,
                "connected": bool(pipe),
                "pipe": pipe,
                "preset": preset_name,
                "client_id": client_id,
                "presence": presence.to_payload_dict(),
            }
            print(json.dumps(data, indent=2))
            return 0

        card = render_discord_card(
            presence,
            client_name="JettsTUI",
            is_connected=bool(pipe),
            pipe_path=pipe,
        )

        if console:
            console.print(card)
            status_note = "[green]Enabled in config[/green]" if is_enabled else "[yellow]Disabled in config (run 'jettstui rpc on' to activate)[/yellow]"
            console.print(f"Status: {status_note} • Preset: [bold cyan]{preset_name}[/bold cyan]")
        else:
            print(card)
            print(f"Enabled: {is_enabled} • Preset: {preset_name}")
        return 0

    elif action in ("on", "enable"):
        save_config_value("discord_rpc.enabled", True)
        if console:
            console.print("[bold green]✓ Discord Rich Presence enabled![/bold green] It will show on your profile during sessions.")
        else:
            print("✓ Discord Rich Presence enabled.")
        return 0

    elif action in ("off", "disable"):
        save_config_value("discord_rpc.enabled", False)
        # Also stop active instance if running
        stop_rpc = getattr(args, "stop_rpc", None)
        if console:
            console.print("[yellow]Discord Rich Presence disabled.[/yellow]")
        else:
            print("Discord Rich Presence disabled.")
        return 0

    elif action == "preset":
        preset_name = args.name
        save_config_value("discord_rpc.preset", preset_name)
        preset_info = PRESETS[preset_name]
        if console:
            console.print(f"[bold green]✓ Switched preset to [cyan]{preset_name}[/cyan]:[/bold green] {preset_info['description']}")
        else:
            print(f"✓ Switched preset to {preset_name}: {preset_info['description']}")
        return 0

    elif action == "set":
        updated = []
        if getattr(args, "client_id", None):
            save_config_value("discord_rpc.client_id", args.client_id)
            updated.append(f"client_id: {args.client_id}")
        if getattr(args, "details", None) is not None:
            save_config_value("discord_rpc.details", args.details)
            updated.append("details")
        if getattr(args, "state", None) is not None:
            save_config_value("discord_rpc.state", args.state)
            updated.append("state")
        if console:
            console.print(f"[bold green]✓ Updated Discord RPC config:[/bold green] {', '.join(updated) if updated else 'no changes'}")
        else:
            print(f"✓ Updated Discord RPC config: {', '.join(updated) if updated else 'no changes'}")
        return 0

    elif action == "test":
        client_id = rpc_cfg.get("client_id") or DEFAULT_CLIENT_ID
        preset_name = getattr(args, "preset", "pairing")
        duration = getattr(args, "duration", 15)

        mgr = DiscordRPCManager(
            client_id=client_id,
            preset=preset_name,
            buttons=rpc_cfg.get("buttons"),
            enabled=True,
        )
        if getattr(args, "state", None) or getattr(args, "details", None):
            mgr.set_custom(state=args.state, details=args.details)

        presence = mgr.build_current_presence()

        if console:
            console.print(f"[bold cyan]Testing Discord Rich Presence with preset '{preset_name}'...[/bold cyan]")

        async def run_test():
            client = DiscordIPCClient(client_id=client_id)
            connected = await client.connect()
            if not connected:
                err_detail = f": {client.last_error}" if client.last_error else ""
                if console:
                    console.print(f"[bold red]✗ Could not connect to Discord{err_detail}.[/bold red]")
                    if "Invalid Client ID" in (client.last_error or ""):
                        console.print("[yellow]💡 Tip: Set a valid Discord Application ID via 'jettstui rpc set --client-id <ID>'[/yellow]")
                        console.print("[dim]Create one in 30 seconds at: https://discord.com/developers/applications[/dim]")
                    else:
                        console.print("[dim]Make sure the Discord desktop app is running on this machine.[/dim]")
                else:
                    print(f"✗ Could not connect to Discord{err_detail}.")
                return 1

            if console:
                console.print(f"[green]✓ Connected to Discord IPC pipe: {client.pipe_path}[/green]")
                console.print("[bold #5865F2]🚀 Setting Rich Presence activity...[/bold #5865F2]")

            ok = await client.set_activity(presence)
            if not ok:
                if console:
                    console.print("[red]✗ Discord rejected the activity payload.[/red]")
                else:
                    print("✗ Discord rejected activity.")
                return 1

            if console:
                console.print("[bold green]✨ Activity sent successfully! Check your Discord profile.[/bold green]")
                if duration > 0:
                    console.print(f"[dim]Keeping presence alive for {duration} seconds (Ctrl+C to stop)...[/dim]")
            else:
                print("✨ Activity sent successfully! Check your Discord profile.")

            try:
                if duration > 0:
                    await asyncio.sleep(duration)
                else:
                    while True:
                        await asyncio.sleep(1)
            except asyncio.CancelledError:
                pass
            finally:
                await client.clear_activity()
                await client.close()
                if console:
                    console.print("[dim]Presence cleared and disconnected.[/dim]")
            return 0

        try:
            if platform.system().lower() == "windows":
                loop = asyncio.ProactorEventLoop()
            else:
                loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(run_test())
        except KeyboardInterrupt:
            if console:
                console.print("\n[yellow]Test interrupted.[/yellow]")
            return 0

    elif action == "daemon":
        preset_name = getattr(args, "preset", "pairing")
        client_id = rpc_cfg.get("client_id") or DEFAULT_CLIENT_ID
        if console:
            console.print(f"[bold #5865F2]Starting JettsTUI Discord RPC Daemon ({preset_name})...[/bold #5865F2]")
            console.print("[dim]Press Ctrl+C to terminate.[/dim]")

        mgr = DiscordRPCManager(
            client_id=client_id,
            preset=preset_name,
            buttons=rpc_cfg.get("buttons"),
            enabled=True,
        )
        mgr.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            mgr.stop()
            if console:
                console.print("\n[yellow]Daemon stopped.[/yellow]")
            return 0

    return 0
