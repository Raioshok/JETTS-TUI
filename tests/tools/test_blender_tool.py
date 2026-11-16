"""Unit tests for Blender 3D tools and script generator."""

import json
import unittest
from unittest.mock import MagicMock, patch

from tools.blender_script_gen import find_blender_binary, generate_blender_script
from tools.blender_tool import (
    _check_blender_available,
    blender_render,
    blender_run_script,
    blender_status,
)
from tools.registry import registry


class TestBlenderTools(unittest.TestCase):
    """Test Blender toolset registration and execution."""

    def test_tools_registered_in_registry(self):
        """Verify blender tools are registered in the global ToolRegistry."""
        from tools.registry import discover_builtin_tools
        discover_builtin_tools()

        tools = registry.get_available_toolsets()
        self.assertIn("blender-3d", tools)
        blender_tools = tools["blender-3d"]["tools"]
        self.assertIn("blender_status", blender_tools)
        self.assertIn("blender_render", blender_tools)
        self.assertIn("blender_run_script", blender_tools)

    def test_script_generation_nature(self):
        """Verify nature scene script generation produces valid bpy calls."""
        script = generate_blender_script(
            prompt="A low poly pine forest with campfire",
            output_path="/tmp/test_output.glb",
            output_format="glb",
            preset="nature",
        )
        self.assertIn("import bpy", script)
        self.assertIn("_build_nature_scene", script)
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
        self.assertIn("_build_architecture_scene", script)
        self.assertIn("export_scene.gltf", script)

    def test_script_generation_scifi(self):
        """Verify scifi preset produces energy core and containment rings."""
        script = generate_blender_script(
            prompt="Futuristic quantum reactor with neon rings",
            output_path="/tmp/reactor.glb",
            output_format="glb",
            preset="scifi",
        )
        self.assertIn("_build_scifi_scene", script)

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
