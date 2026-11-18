"""Unit tests for Blender 3D tools, toolset wiring, and script generator."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.blender_script_gen import (
    generate_blender_script,
    parse_prompt_attributes,
    wrap_custom_bpy_script,
)
from tools.blender_tool import (
    blender_render,
    blender_run_script,
    blender_status,
)
from tools.registry import discover_builtin_tools, registry
from toolsets import _JETTSTUI_CORE_TOOLS, resolve_toolset


class TestBlenderTools(unittest.TestCase):
    """Test Blender toolset registration, gating, and execution."""

    def test_tools_registered_in_registry_and_core_toolsets(self):
        """Verify blender tools are registered in ToolRegistry and wired into toolsets.py."""
        discover_builtin_tools()

        tools = registry.get_available_toolsets()
        self.assertIn("blender-3d", tools)
        blender_tools = tools["blender-3d"]["tools"]
        self.assertIn("blender_status", blender_tools)
        self.assertIn("blender_render", blender_tools)
        self.assertIn("blender_run_script", blender_tools)

        # Wired into core tools and resolvable by toolset name + alias
        for name in ("blender_status", "blender_render", "blender_run_script"):
            self.assertIn(name, _JETTSTUI_CORE_TOOLS)
            self.assertIn(name, resolve_toolset("blender-3d"))
            self.assertIn(name, resolve_toolset("blender"))

    def test_script_generation_nature(self):
        """Verify nature scene script generation produces valid bpy calls."""
        script = generate_blender_script(
            prompt="A low poly pine forest with campfire",
            output_path="/tmp/test_output.glb",
            output_format="glb",
            preset="nature",
        )
        self.assertIn("import bpy", script)
        self.assertIn("_build_nature_scene()", script)
        self.assertIn("export_scene.gltf", script)
        self.assertIn("/tmp/test_output.glb", script)

    def test_script_generation_architecture(self):
        """Verify architecture preset produces building primitives."""
        script = generate_blender_script(
            prompt="A cozy mountain cabin with chimney and door",
            output_path="/tmp/cabin.glb",
            output_format="glb",
            preset="architecture",
        )
        self.assertIn("_build_architecture_scene()", script)
        self.assertIn("export_scene.gltf", script)

    def test_script_generation_scifi(self):
        """Verify scifi preset produces energy core and containment rings."""
        script = generate_blender_script(
            prompt="Futuristic quantum reactor with neon rings",
            output_path="/tmp/reactor.glb",
            output_format="glb",
            preset="scifi",
        )
        self.assertIn("_build_scifi_scene()", script)

    def test_script_generation_custom_primitives_and_colors(self):
        """Verify general primitive/color prompts build matching shapes instead of a chest."""
        attrs = parse_prompt_attributes("Four glowing red metallic spheres")
        self.assertEqual(attrs["primitive"], "sphere")
        self.assertEqual(attrs["count"], 4)
        self.assertGreater(attrs["metallic"], 0.8)
        self.assertGreater(attrs["emission_strength"], 0.0)

        script = generate_blender_script(
            prompt="Four glowing red metallic spheres",
            output_path="/tmp/spheres.glb",
            output_format="glb",
            preset="auto",
        )
        self.assertIn("_build_custom_primitive_scene(", script)
        self.assertIn("shape='sphere'", script)
        self.assertIn("count=4", script)

    def test_wrap_custom_bpy_script_injects_output_target(self):
        """Verify custom bpy scripts receive JETTSTUI_BLENDER_OUTPUT_PATH and auto-export guard."""
        wrapped = wrap_custom_bpy_script(
            "import bpy\nbpy.ops.mesh.primitive_monkey_add()",
            output_path="C:\\temp\\suzanne.glb",
            output_format="glb",
        )
        self.assertIn("JETTSTUI_BLENDER_OUTPUT_PATH", wrapped)
        self.assertIn("C:/temp/suzanne.glb", wrapped)
        self.assertIn("_jettstui_ensure_output()", wrapped)

    def test_script_generation_render_png(self):
        """Verify PNG rendering script configures render engine and write_still."""
        script = generate_blender_script(
            prompt="Photorealistic crystal ball on marble",
            output_path="/tmp/render.png",
            output_format="png",
            quality="draft",
        )
        self.assertIn("render.engine", script)
        self.assertIn("bpy.ops.render.render(write_still=True)", script)
        self.assertIn("BLENDER_EEVEE_NEXT", script)

    def test_blender_status_when_not_installed(self):
        """Verify blender_status returns clean json when binary is absent."""
        with patch("tools.blender_tool.find_blender_binary", return_value=None):
            result_json = blender_status()
            data = json.loads(result_json)
            self.assertFalse(data.get("available"))
            self.assertIn("not detected", data.get("message", "").lower())

    def test_blender_render_when_not_installed(self):
        """Verify blender_render returns informative error if blender is missing."""
        with patch("tools.blender_tool.find_blender_binary", return_value=None):
            result_json = blender_render(prompt="A test cube")
            data = json.loads(result_json)
            self.assertIn("error", data)
            self.assertIn("not found", data["error"].lower())

    def test_blender_render_rejects_missing_output_file(self):
        """Verify blender_render errors when subprocess exits 0 without writing the target file."""
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch("tools.blender_tool._get_output_dir", return_value=Path(tmp)),
                patch("tools.blender_tool._execute_blender_script", return_value={"success": True, "stdout": "ok", "duration_seconds": 0.5}),
            ):
                result_json = blender_render(prompt="Empty script", custom_bpy_script="pass")
                data = json.loads(result_json)
                self.assertFalse(data.get("success", True))
                self.assertIn("without producing output file", data.get("error", ""))

    def test_blender_run_script_omits_output_path_when_not_created(self):
        """Verify blender_run_script reports output_exists=False when no file was written."""
        with patch("tools.blender_tool._execute_blender_script", return_value={"success": True, "stdout": "Scene stats: 4 objs", "duration_seconds": 0.2}):
            result_json = blender_run_script(script="print('hello')")
            data = json.loads(result_json)
            self.assertTrue(data["success"])
            self.assertFalse(data["output_exists"])
            self.assertIsNone(data["output_path"])

    def test_blender_render_empty_prompt(self):
        """Verify blender_render rejects empty prompt."""
        result_json = blender_render(prompt="")
        data = json.loads(result_json)
        self.assertIn("error", data)

    def test_blender_run_script_empty(self):
        """Verify blender_run_script rejects empty script."""
        result_json = blender_run_script(script="")
        data = json.loads(result_json)
        self.assertIn("error", data)


if __name__ == "__main__":
    unittest.main()
