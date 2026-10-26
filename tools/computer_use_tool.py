"""Shim for tool discovery. Registers `computer_use` with tools.registry.

The real implementation lives in the `tools/computer_use/` package to keep
the file structure clean. This shim exists because tools.registry auto-imports
`tools/*.py` — we need a top-level module to trigger the registration.
"""

from __future__ import annotations

from tools.computer_use.schema import COMPUTER_USE_SCHEMA, VM_SCHEMA
from tools.computer_use.tool import (
    check_computer_use_requirements,
    handle_computer_use,
    set_approval_callback,
)
from tools.computer_use.vm_manager import check_vm_requirements
from tools.registry import registry


registry.register(
    name="computer_use",
    toolset="computer_use",
    schema=COMPUTER_USE_SCHEMA,
    handler=lambda args, **kw: handle_computer_use(args, **kw),
    check_fn=check_computer_use_requirements,
    requires_env=[],
    description=(
        "Universal desktop control (macOS, Windows, Linux) — screenshot, mouse, "
        "keyboard, scroll, drag; target=<vm> drives a VM guest. Works with any "
        "tool-capable model."
    ),
)

# VM lifecycle shares computer_use's dispatch + approval gate; its schema only
# ships when a hypervisor or registered VPS exists.
registry.register(
    name="vm",
    toolset="computer_use",
    schema=VM_SCHEMA,
    handler=lambda args, **kw: handle_computer_use(args, **kw),
    check_fn=check_vm_requirements,
    requires_env=[],
    description="VM/VPS lifecycle, snapshots, guest commands and file transfer.",
)


__all__ = [
    "handle_computer_use",
    "set_approval_callback",
    "check_computer_use_requirements",
    "VMManager",
    "get_vm_manager",
]
