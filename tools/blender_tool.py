"""Blender 3D generation and rendering tool.

Enables the AI agent to generate procedural 3D models (GLB), set up materials,
lighting, cameras, execute bpy scripts, and produce photorealistic raytraced renders
via a headless Blender process.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

from jettstui_constants import get_jettstui_home
from tools.blender_script_gen import (
    find_blender_binary,
    generate_blender_script,
    wrap_custom_bpy_script,
)
from tools.registry import registry, tool_error, tool_result

logger = logging.getLogger(__name__)

BLENDER_TOOLSET = "blender-3d"


def _check_blender_available() -> bool:
    """Check if Blender executable exists on the system."""
    return find_blender_binary() is not None


def _get_output_dir() -> Path:
    """Ensure and return the output directory for generated 3D models."""
    out_dir = get_jettstui_home() / "blender_models"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _execute_blender_script(
    script_code: str,
    timeout_seconds: int = 120,
    extra_env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Execute a Python bpy script in headless Blender and capture output."""
    blender_bin = find_blender_binary()
    if not blender_bin:
        return {
            "success": False,
            "error": (
                "Blender binary not found on this system. "
                "Please install Blender (https://www.blender.org/download/) or add it to PATH."
            ),
        }

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(script_code)
        temp_script_path = f.name

    run_env = os.environ.copy()
    if extra_env:
        run_env.update(extra_env)

    try:
        cmd = [
            blender_bin,
            "--background",
            "--python",
            temp_script_path,
        ]

        start_time = time.time()
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
            encoding="utf-8",
            errors="replace",
            env=run_env,
        )
        duration = round(time.time() - start_time, 2)

        if proc.returncode != 0:
            return {
                "success": False,
                "error": f"Blender exited with code {proc.returncode}",
                "stdout": proc.stdout[-1500:] if proc.stdout else "",
                "stderr": proc.stderr[-1500:] if proc.stderr else "",
                "duration_seconds": duration,
            }

        return {
            "success": True,
            "stdout": proc.stdout[-800:] if proc.stdout else "",
            "duration_seconds": duration,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"Blender execution timed out after {timeout_seconds} seconds.",
        }
    except Exception as exc:
        return {
            "success": False,
            "error": f"Failed to execute Blender process: {exc}",
        }
    finally:
        try:
            if os.path.exists(temp_script_path):
                os.remove(temp_script_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Tool Handlers
# ---------------------------------------------------------------------------

def blender_status() -> str:
    """Return status and version of the local Blender installation."""
    blender_bin = find_blender_binary()
    if not blender_bin:
        return tool_result({
            "available": False,
            "message": "Blender is not detected. Install Blender from blender.org to enable 3D model generation.",
            "path": None,
            "version": None,
        })

    version_str = "Unknown"
    try:
        proc = subprocess.run(
            [blender_bin, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            encoding="utf-8",
            errors="replace",
        )
        if proc.stdout:
            for line in proc.stdout.splitlines():
                if "Blender" in line:
                    version_str = line.strip()
                    break
    except Exception as exc:
        logger.warning("Failed to query Blender version: %s", exc)

    return tool_result({
        "available": True,
        "path": blender_bin,
        "version": version_str,
        "models_dir": str(_get_output_dir()),
    })


def blender_render(
    prompt: str,
    output_format: str = "glb",
    preset: str = "auto",
    quality: str = "draft",
    custom_bpy_script: Optional[str] = None,
) -> str:
    """Generate or render a 3D model/scene using Blender."""
    if not prompt and not custom_bpy_script:
        return tool_error("Either 'prompt' or 'custom_bpy_script' must be provided.")

    out_dir = _get_output_dir()
    timestamp = int(time.time())
    safe_name = "".join(c if c.isalnum() else "_" for c in (prompt or "custom")[:25].strip()).strip("_") or "model"

    fmt = output_format.lower()
    ext = ".glb" if fmt in ["glb", "gltf"] else ".png"
    filename = f"{safe_name}_{timestamp}{ext}"
    output_filepath = out_dir / filename

    if custom_bpy_script:
        script = wrap_custom_bpy_script(
            custom_script=custom_bpy_script,
            output_path=str(output_filepath),
            output_format=fmt,
            quality=quality,
        )
    else:
        script = generate_blender_script(
            prompt=prompt,
            output_path=str(output_filepath),
            output_format=fmt,
            preset=preset,
            quality=quality,
        )

    res = _execute_blender_script(
        script,
        timeout_seconds=120,
        extra_env={
            "JETTSTUI_BLENDER_OUTPUT_PATH": str(output_filepath),
            "JETTSTUI_BLENDER_FORMAT": fmt,
        },
    )

    if not res.get("success"):
        return tool_error(
            res.get("error", "Blender generation failed"),
            stdout=res.get("stdout"),
            stderr=res.get("stderr"),
            success=False,
        )

    if not output_filepath.is_file() or output_filepath.stat().st_size == 0:
        return tool_error(
            f"Blender finished without producing output file at {output_filepath}",
            stdout=res.get("stdout"),
            stderr=res.get("stderr"),
            success=False,
        )

    file_size_bytes = output_filepath.stat().st_size

    return tool_result({
        "success": True,
        "prompt": prompt,
        "format": fmt,
        "output_path": str(output_filepath),
        "output_exists": True,
        "filename": filename,
        "file_size_bytes": file_size_bytes,
        "duration_seconds": res.get("duration_seconds", 0),
        "message": f"Successfully generated {fmt.upper()} at {output_filepath}",
    })


def blender_run_script(script: str, output_path: Optional[str] = None) -> str:
    """Run an arbitrary Blender Python (bpy) script directly."""
    if not script or not script.strip():
        return tool_error("Empty script provided.")

    extra_env = {"JETTSTUI_BLENDER_OUTPUT_PATH": output_path} if output_path else None
    res = _execute_blender_script(script, timeout_seconds=180, extra_env=extra_env)
    if not res.get("success"):
        return tool_error(
            res.get("error", "Script execution failed"),
            stdout=res.get("stdout"),
            stderr=res.get("stderr"),
            success=False,
        )

    resolved_out = Path(output_path) if output_path else None
    output_exists = bool(resolved_out and resolved_out.is_file() and resolved_out.stat().st_size > 0)
    file_size_bytes = resolved_out.stat().st_size if output_exists and resolved_out else 0

    return tool_result({
        "success": True,
        "duration_seconds": res.get("duration_seconds", 0),
        "output_path": output_path if output_exists else None,
        "filename": resolved_out.name if output_exists and resolved_out else None,
        "file_size_bytes": file_size_bytes if output_exists else None,
        "output_exists": output_exists,
        "stdout": res.get("stdout", ""),
    })


# ---------------------------------------------------------------------------
# Schemas & Registration
# ---------------------------------------------------------------------------

BLENDER_STATUS_SCHEMA = {
    "name": "blender_status",
    "description": "Check if Blender is installed locally, get version and executable path.",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}

BLENDER_RENDER_SCHEMA = {
    "name": "blender_render",
    "description": (
        "Generate a 3D model (GLB) or rendered image (PNG) using Blender. "
        "Can generate from a natural language prompt or a custom bpy Python script "
        "(which may read os.environ['JETTSTUI_BLENDER_OUTPUT_PATH'] or leave the scene ready for auto-export)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Description of the 3D model, prop, building, or scene to generate.",
            },
            "output_format": {
                "type": "string",
                "enum": ["glb", "png"],
                "default": "glb",
                "description": "Output format: 'glb' for an interactive 3D model, 'png' for a rendered still image.",
            },
            "preset": {
                "type": "string",
                "enum": ["auto", "nature", "architecture", "scifi", "furniture", "abstract"],
                "default": "auto",
                "description": "Style and geometry preset archetype.",
            },
            "quality": {
                "type": "string",
                "enum": ["draft", "final"],
                "default": "draft",
                "description": "Render quality: 'draft' uses EEVEE, 'final' uses Cycles with higher sample counts.",
            },
            "custom_bpy_script": {
                "type": "string",
                "description": "Optional complete Blender Python (bpy) script. Auto-exported to GLB/PNG if it does not write JETTSTUI_BLENDER_OUTPUT_PATH directly.",
            },
        },
        "required": ["prompt"],
    },
}

BLENDER_RUN_SCRIPT_SCHEMA = {
    "name": "blender_run_script",
    "description": "Run an arbitrary Blender Python (bpy) script headless in Blender. Returns execution logs and result.",
    "parameters": {
        "type": "object",
        "properties": {
            "script": {
                "type": "string",
                "description": "The complete Python script using the bpy module to execute.",
            },
            "output_path": {
                "type": "string",
                "description": "Optional path where the script saves a 3D model or render.",
            },
        },
        "required": ["script"],
    },
}

registry.register_toolset_alias("blender", BLENDER_TOOLSET)

registry.register(
    name="blender_status",
    toolset=BLENDER_TOOLSET,
    schema=BLENDER_STATUS_SCHEMA,
    handler=lambda args, **kw: blender_status(),
    check_fn=_check_blender_available,
    emoji="🧊",
)

registry.register(
    name="blender_render",
    toolset=BLENDER_TOOLSET,
    schema=BLENDER_RENDER_SCHEMA,
    handler=lambda args, **kw: blender_render(
        prompt=args.get("prompt", ""),
        output_format=args.get("output_format", "glb"),
        preset=args.get("preset", "auto"),
        quality=args.get("quality", "draft"),
        custom_bpy_script=args.get("custom_bpy_script"),
    ),
    check_fn=_check_blender_available,
    emoji="🎨",
)

registry.register(
    name="blender_run_script",
    toolset=BLENDER_TOOLSET,
    schema=BLENDER_RUN_SCRIPT_SCHEMA,
    handler=lambda args, **kw: blender_run_script(
        script=args.get("script", ""),
        output_path=args.get("output_path"),
    ),
    check_fn=_check_blender_available,
    emoji="⚙️",
)
