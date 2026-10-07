"""Smoke tests for the batch-extracted subcommand parser builders.

Each ``build_<group>_parser`` should attach its subcommand to a subparsers
group and wire ``func`` to the injected handler. These are intentionally
light — the byte-identical ``--help`` verification done at extraction time is
the real behavioral guarantee; this just guards against a module failing to
import or a builder raising.
"""

from __future__ import annotations

import argparse

import pytest

from jettstui.subcommands.auth import build_auth_parser
from jettstui.subcommands.backup import build_backup_parser
from jettstui.subcommands.config import build_config_parser
from jettstui.subcommands.dashboard import build_dashboard_parser
from jettstui.subcommands.debug import build_debug_parser
from jettstui.subcommands.doctor import build_doctor_parser
from jettstui.subcommands.dump import build_dump_parser
from jettstui.subcommands.gui import build_gui_parser
from jettstui.subcommands.hooks import build_hooks_parser
from jettstui.subcommands.import_cmd import build_import_cmd_parser
from jettstui.subcommands.login import build_login_parser
from jettstui.subcommands.logout import build_logout_parser
from jettstui.subcommands.logs import build_logs_parser
from jettstui.subcommands.model import build_model_parser

from jettstui.subcommands.prompt_size import build_prompt_size_parser
from jettstui.subcommands.security import build_security_parser
from jettstui.subcommands.setup import build_setup_parser
from jettstui.subcommands.slack import build_slack_parser
from jettstui.subcommands.status import build_status_parser
from jettstui.subcommands.uninstall import build_uninstall_parser
from jettstui.subcommands.update import build_update_parser
from jettstui.subcommands.version import build_version_parser
from jettstui.subcommands.webhook import build_webhook_parser
from jettstui.subcommands.whatsapp import build_whatsapp_parser


def _h(name):
    def handler(args):  # pragma: no cover - identity only
        return name
    handler.__name__ = f"cmd_{name}"
    return handler


# (subcommand_name, builder, handler_kwargs, sample_argv)
SINGLE_HANDLER_CASES = [
    ("model", build_model_parser, "cmd_model", ["model"]),
    ("setup", build_setup_parser, "cmd_setup", ["setup"]),

    ("whatsapp", build_whatsapp_parser, "cmd_whatsapp", ["whatsapp"]),
    ("slack", build_slack_parser, "cmd_slack", ["slack"]),
    ("login", build_login_parser, "cmd_login", ["login"]),
    ("logout", build_logout_parser, "cmd_logout", ["logout"]),
    ("auth", build_auth_parser, "cmd_auth", ["auth"]),
    ("status", build_status_parser, "cmd_status", ["status"]),
    ("webhook", build_webhook_parser, "cmd_webhook", ["webhook"]),
    ("hooks", build_hooks_parser, "cmd_hooks", ["hooks"]),
    ("doctor", build_doctor_parser, "cmd_doctor", ["doctor"]),
    ("security", build_security_parser, "cmd_security", ["security"]),
    ("dump", build_dump_parser, "cmd_dump", ["dump"]),
    ("debug", build_debug_parser, "cmd_debug", ["debug"]),
    ("backup", build_backup_parser, "cmd_backup", ["backup"]),
    ("import", build_import_cmd_parser, "cmd_import", ["import", "/tmp/x.zip"]),
    ("config", build_config_parser, "cmd_config", ["config"]),
    ("version", build_version_parser, "cmd_version", ["version"]),
    ("update", build_update_parser, "cmd_update", ["update"]),
    ("uninstall", build_uninstall_parser, "cmd_uninstall", ["uninstall"]),
    ("gui", build_gui_parser, "cmd_gui", ["gui"]),
    ("logs", build_logs_parser, "cmd_logs", ["logs"]),
    ("prompt-size", build_prompt_size_parser, "cmd_prompt_size", ["prompt-size"]),
]


@pytest.mark.parametrize("name,builder,kw,argv", SINGLE_HANDLER_CASES, ids=[c[0] for c in SINGLE_HANDLER_CASES])
def test_single_handler_builders(name, builder, kw, argv):
    parser = argparse.ArgumentParser(prog="jettstui")
    sub = parser.add_subparsers(dest="command")
    handler = _h(name)
    builder(sub, **{kw: handler})
    ns = parser.parse_args(argv)
    assert ns.func is handler


def test_config_get_unset_subcommands_parse():
    """`jettstui config get/unset` parse key args (and --json for get)."""
    parser = argparse.ArgumentParser(prog="jettstui")
    sub = parser.add_subparsers(dest="command")
    handler = _h("config")
    build_config_parser(sub, cmd_config=handler)

    ns = parser.parse_args(["config", "get", "terminal.backend", "--json"])
    assert ns.func is handler
    assert ns.config_command == "get"
    assert ns.key == "terminal.backend"
    assert ns.json is True

    ns = parser.parse_args(["config", "unset", "terminal.backend"])
    assert ns.func is handler
    assert ns.config_command == "unset"
    assert ns.key == "terminal.backend"


def test_dashboard_builder_launches_dashboard():
    parser = argparse.ArgumentParser(prog="jettstui")
    sub = parser.add_subparsers(dest="command")
    dash = _h("dashboard")
    build_dashboard_parser(sub, cmd_dashboard=dash)
    # bare dashboard -> launch handler
    assert parser.parse_args(["dashboard"]).func is dash


# ── deprecated `jettstui login` fails gracefully, not with argparse error ────
#
# `jettstui login` is a removed command; its handler (`login_command` in
# `jettstui/auth.py`) prints a deprecation notice pointing at `jettstui auth` /
# `jettstui model` and exits 0.  Two behavior contracts guard the UX:
#   1. ANY `--provider <value>` (including ones the user actually wants, like
#      `anthropic`) must parse and reach the handler — never crash in argparse
#      with `invalid choice` before the friendly redirect is printed (#24756).
#   2. The subcommand must not advertise itself in the parser help row.


def _login_parser():
    parser = argparse.ArgumentParser(prog="jettstui")
    sub = parser.add_subparsers(dest="command")
    build_login_parser(sub, cmd_login=_h("login"))
    return parser


@pytest.mark.parametrize("provider", ["anthropic", "nous", "openai-codex", "totally-made-up"])
def test_login_accepts_any_provider_value(provider):
    """Deprecated `login` must route every `--provider` to the handler.

    A restrictive `choices=` list (the pre-fix behavior) rejected providers
    like `anthropic` with an argparse error *before* the deprecation message
    could run, so the user just saw `invalid choice: 'anthropic'` and assumed
    the feature was broken rather than relocated.
    """
    ns = _login_parser().parse_args(["login", "--provider", provider])
    assert ns.func.__name__ == "cmd_login"
    assert ns.provider == provider


def test_login_subparser_help_is_suppressed():
    """The deprecated `login` row must not appear in `jettstui --help`.

    Must hold without leaking argparse's literal `==SUPPRESS==` placeholder,
    which `help=argparse.SUPPRESS` emits for a top-level subparser on 3.12+.
    The fix omits the `help=` kwarg entirely instead.
    """
    parser = argparse.ArgumentParser(prog="jettstui")
    sub = parser.add_subparsers(dest="command")
    build_login_parser(sub, cmd_login=_h("login"))
    help_text = parser.format_help()
    # The misleading old help string must be gone from the top-level usage.
    assert "Authenticate with an inference provider" not in help_text
    # And no leaked SUPPRESS placeholder row.
    assert "==SUPPRESS==" not in help_text
