"""Discord Presence backend routes, mounted at /api/plugins/discord-presence/.

Used by the Desktop settings tab. Routes sit behind the dashboard's normal
session-token auth (they are not public paths). Endpoints are plain ``def``
so FastAPI runs them in its threadpool — the Application ID lookup and
config writes block.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

_PACKAGE = "jettstui_plugins.discord_presence"
_PLUGIN_DIR = Path(__file__).resolve().parent.parent


def _plugin() -> types.ModuleType:
    """Import the plugin package under the name the plugin loader uses.

    Sharing the module name means the presence service singleton (in the
    ``service`` submodule) is the same object the agent hooks drive, whether
    the plugin loader or this API imported it first.
    """
    module = sys.modules.get(_PACKAGE)
    if module is not None:
        return module
    parent = _PACKAGE.rsplit(".", 1)[0]
    if parent not in sys.modules:
        ns = types.ModuleType(parent)
        ns.__path__ = []  # type: ignore[attr-defined]
        sys.modules[parent] = ns
    spec = importlib.util.spec_from_file_location(
        _PACKAGE, _PLUGIN_DIR / "__init__.py", submodule_search_locations=[str(_PLUGIN_DIR)]
    )
    if spec is None or spec.loader is None:
        raise HTTPException(status_code=500, detail="Discord presence plugin is missing")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_PACKAGE] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(_PACKAGE, None)
        raise
    return module


def _call(fn, *args: Any) -> Dict[str, Any]:
    try:
        return fn(*args)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


class EnabledBody(BaseModel):
    enabled: bool


class ClientIdBody(BaseModel):
    client_id: str


class SettingsBody(BaseModel):
    changes: Dict[str, Any]


@router.get("/status")
def status() -> Dict[str, Any]:
    return _plugin().service.get_service().status()


@router.post("/enabled")
def set_enabled(body: EnabledBody) -> Dict[str, Any]:
    return _call(_plugin().commands.set_enabled, body.enabled)


@router.post("/application")
def set_application(body: ClientIdBody) -> Dict[str, Any]:
    plugin = _plugin()
    app = _call(plugin.commands.set_client_id, body.client_id)
    return {"application": app, "status": plugin.service.get_service().status()}


@router.get("/application")
def lookup_application(client_id: Optional[str] = None) -> Dict[str, Any]:
    plugin = _plugin()
    target = client_id or plugin.service.get_service().settings(fresh=True).client_id
    if not target:
        raise HTTPException(status_code=404, detail="No Discord Application ID configured")
    return _call(plugin.service.lookup_application, target)


@router.patch("/settings")
def update_settings(body: SettingsBody) -> Dict[str, Any]:
    return _call(_plugin().commands.update_settings, body.changes)


@router.post("/refresh")
def refresh() -> Dict[str, Any]:
    service = _plugin().service.get_service()
    service.refresh()
    return service.status()
