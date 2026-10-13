"""``jettstui model`` subcommand parser.

Extracted verbatim from ``jettstui/main.py:main()`` (god-file Phase 2).
Handler injected to avoid importing ``main``.
"""

from __future__ import annotations

from typing import Callable


def build_model_parser(subparsers, *, cmd_model: Callable) -> None:
    """Attach the ``model`` subcommand to ``subparsers``."""
    # =========================================================================
    # model command
    # =========================================================================
    model_parser = subparsers.add_parser(
        "model",
        help="Select default model and provider",
        description="Interactively select your inference provider and default model",
    )
    model_parser.add_argument(
        "--refresh",
        action="store_true",
        help="Wipe the model picker disk cache and re-fetch every provider's live /v1/models list.",
    )
    model_parser.add_argument(
        "--update",
        "-u",
        action="store_true",
        help="Automatically check and update model catalogs from all OAuth and API-key providers.",
    )
    model_parser.add_argument(
        "action",
        nargs="?",
        choices=["update", "status"],
        default=None,
        help="Optional action: 'update' to run the model autoupdater, or 'status' to view last update info.",
    )
    model_parser.set_defaults(func=cmd_model)
