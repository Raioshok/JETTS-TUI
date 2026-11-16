"""Unit tests for Blender FastAPI plugin API router (direct async execution)."""

import asyncio
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from plugins.blender.dashboard.plugin_api import (
    GenerateRequest,
    generate_model,
    get_status,
    list_models,
)


class TestBlenderPluginApi(unittest.TestCase):
    """Test Blender dashboard plugin API endpoints directly."""

    def test_status_endpoint(self):
        """Test get_status() handler."""
        with patch("plugins.blender.dashboard.plugin_api.find_blender_binary", return_value=None):
            data = asyncio.run(get_status())
            self.assertFalse(data["available"])
            self.assertEqual(data["version"], "Not installed")

    def test_models_endpoint(self):
        """Test list_models() handler."""
        data = asyncio.run(list_models())
        self.assertIn("models", data)
        self.assertIsInstance(data["models"], list)

    def test_generate_requires_blender(self):
        """Test generate_model() raises 503 if Blender not installed."""
        req = GenerateRequest(
            prompt="Low poly pine tree",
            format="glb",
            preset="nature",
            quality="draft",
        )
        with patch("plugins.blender.dashboard.plugin_api.find_blender_binary", return_value=None):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(generate_model(req))
            self.assertEqual(ctx.exception.status_code, 503)
            self.assertIn("not installed", str(ctx.exception.detail).lower())


if __name__ == "__main__":
    unittest.main()
