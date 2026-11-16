"""Blender 3D plugin backend API router.

Mounted at /api/plugins/blender/ by the dashboard plugin engine.
Provides REST and WebSocket endpoints for 3D generation, model inspection,
file downloads, and live status.
"""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect, status as http_status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from jettstui_constants import get_jettstui_home
from tools.blender_script_gen import find_blender_binary, generate_blender_script
from tools.blender_tool import _execute_blender_script, _get_output_dir, blender_status

logger = logging.getLogger(__name__)

router = APIRouter()

# Active WebSocket connections for broadcasting render progress
_active_ws: List[WebSocket] = []


def _broadcast_event(event: Dict[str, Any]):
    """Broadcast an event to all connected WebSocket clients."""
    payload = json.dumps(event)
    for ws in list(_active_ws):
        try:
            asyncio.create_task(ws.send_text(payload))
        except Exception:
            pass


class GenerateRequest(BaseModel):
    prompt: str = Field(..., description="Prompt describing the 3D model or scene")
    format: str = Field("glb", description="'glb' or 'png'")
    preset: str = Field("auto", description="Style preset: auto, nature, architecture, scifi, furniture, abstract")
    quality: str = Field("draft", description="'draft' or 'final'")
    script: Optional[str] = Field(None, description="Optional raw bpy script")


class ScriptRequest(BaseModel):
    script: str = Field(..., description="Complete Python script using bpy")


@router.get("/status")
async def get_status():
    """Return local Blender installation status and capabilities."""
    binary = find_blender_binary()
    output_dir = _get_output_dir()
    available = binary is not None

    version = "Not installed"
    if available:
        try:
            import subprocess
            proc = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=5)
            for line in proc.stdout.splitlines():
                if "Blender" in line:
                    version = line.strip()
                    break
        except Exception:
            version = "Installed (version query failed)"

    return {
        "available": available,
        "version": version,
        "path": binary,
        "output_dir": str(output_dir),
    }


@router.get("/models")
async def list_models():
    """List all generated 3D models and renders."""
    out_dir = _get_output_dir()
    items = []

    if out_dir.is_dir():
        for file in sorted(out_dir.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True):
            if file.is_file() and file.suffix.lower() in [".glb", ".gltf", ".png", ".jpg", ".obj"]:
                stat = file.stat()
                items.append({
                    "filename": file.name,
                    "url": f"/api/plugins/blender/files/{file.name}",
                    "size_bytes": stat.st_size,
                    "modified_time": int(stat.st_mtime),
                    "format": file.suffix.lower().lstrip("."),
                })

    return {"models": items}


@router.get("/files/{filename}")
async def get_model_file(filename: str):
    """Serve a 3D model or render file safely."""
    # Prevent directory traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    out_dir = _get_output_dir()
    file_path = out_dir / filename

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    # Resolve proper MIME type
    ext = file_path.suffix.lower()
    if ext == ".glb":
        media_type = "model/gltf-binary"
    elif ext == ".gltf":
        media_type = "model/gltf+json"
    elif ext == ".png":
        media_type = "image/png"
    elif ext in [".jpg", ".jpeg"]:
        media_type = "image/jpeg"
    elif ext == ".obj":
        media_type = "text/plain"
    else:
        media_type, _ = mimetypes.guess_type(str(file_path))
        media_type = media_type or "application/octet-stream"

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=filename,
    )


@router.post("/generate")
async def generate_model(req: GenerateRequest):
    """Generate a 3D model (GLB) or render (PNG) from prompt."""
    binary = find_blender_binary()
    if not binary:
        raise HTTPException(
            status_code=503,
            detail="Blender is not installed on this machine. Please install Blender from https://www.blender.org/download/"
        )

    out_dir = _get_output_dir()
    timestamp = int(time.time())
    safe_name = "".join(c if c.isalnum() else "_" for c in req.prompt[:25].strip()).strip("_") or "model"
    fmt = req.format.lower()
    ext = ".glb" if fmt in ["glb", "gltf"] else ".png"
    filename = f"{safe_name}_{timestamp}{ext}"
    output_path = out_dir / filename

    _broadcast_event({
        "type": "render_start",
        "prompt": req.prompt,
        "format": fmt,
        "filename": filename,
    })

    if req.script:
        script = req.script
    else:
        script = generate_blender_script(
            prompt=req.prompt,
            output_path=str(output_path),
            output_format=fmt,
            preset=req.preset,
            quality=req.quality,
        )

    # Run Blender process in thread pool
    res = await asyncio.to_thread(_execute_blender_script, script, 120)

    if not res.get("success"):
        _broadcast_event({
            "type": "render_error",
            "error": res.get("error"),
            "stderr": res.get("stderr"),
        })
        raise HTTPException(
            status_code=500,
            detail={
                "message": res.get("error", "Blender execution failed"),
                "stderr": res.get("stderr", ""),
                "stdout": res.get("stdout", ""),
            }
        )

    file_size = output_path.stat().st_size if output_path.exists() else 0

    response_data = {
        "success": True,
        "filename": filename,
        "url": f"/api/plugins/blender/files/{filename}",
        "format": fmt,
        "size_bytes": file_size,
        "duration_seconds": res.get("duration_seconds", 0),
        "stdout": res.get("stdout", ""),
    }

    _broadcast_event({
        "type": "render_complete",
        **response_data,
    })

    return response_data


@router.post("/execute-script")
async def execute_raw_script(req: ScriptRequest):
    """Run an arbitrary bpy script supplied by user or AI."""
    binary = find_blender_binary()
    if not binary:
        raise HTTPException(status_code=503, detail="Blender binary not found")

    res = await asyncio.to_thread(_execute_blender_script, req.script, 180)
    if not res.get("success"):
        raise HTTPException(
            status_code=500,
            detail={
                "message": res.get("error", "Script error"),
                "stderr": res.get("stderr", ""),
                "stdout": res.get("stdout", ""),
            }
        )

    return {
        "success": True,
        "duration_seconds": res.get("duration_seconds", 0),
        "stdout": res.get("stdout", ""),
    }


@router.post("/upload")
async def upload_model(file: UploadFile = File(...)):
    """Upload an existing local 3D model (GLB, GLTF, OBJ) to view."""
    filename = file.filename or "uploaded_model.glb"
    ext = Path(filename).suffix.lower()
    if ext not in [".glb", ".gltf", ".obj"]:
        raise HTTPException(status_code=400, detail="Only .glb, .gltf, and .obj files are supported")

    out_dir = _get_output_dir()
    safe_name = f"upload_{int(time.time())}_{Path(filename).name}"
    target = out_dir / safe_name

    with target.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {
        "success": True,
        "filename": safe_name,
        "url": f"/api/plugins/blender/files/{safe_name}",
        "size_bytes": target.stat().st_size,
    }


@router.websocket("/events")
async def blender_events_ws(ws: WebSocket):
    """Live WebSocket connection streaming generation progress and status."""
    await ws.accept()
    _active_ws.append(ws)
    try:
        # Send initial status
        binary = find_blender_binary()
        await ws.send_json({
            "type": "connected",
            "blender_available": binary is not None,
            "path": binary,
        })

        while True:
            # Keep-alive loop / receive commands
            msg = await ws.receive_text()
            try:
                data = json.loads(msg)
                action = data.get("action")
                if action == "ping":
                    await ws.send_json({"type": "pong"})
                elif action == "status":
                    b = find_blender_binary()
                    await ws.send_json({
                        "type": "status",
                        "available": b is not None,
                        "path": b,
                    })
            except Exception:
                pass
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        if ws in _active_ws:
            _active_ws.remove(ws)
