"""Unit tests for Blender FastAPI plugin API router (auth, uploads, and generation)."""

import asyncio
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException, UploadFile, status as http_status
from plugins.blender.dashboard import plugin_api
from plugins.blender.dashboard.plugin_api import (
    GenerateRequest,
    blender_events_ws,
    generate_model,
    get_status,
    list_models,
    upload_model,
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

    def test_ws_rejects_unauthorized_upgrade(self):
        """Verify /events WebSocket closes with WS_1008_POLICY_VIOLATION when unauthorized."""
        ws = MagicMock()
        ws.close = AsyncMock()
        ws.accept = AsyncMock()
        with patch("plugins.blender.dashboard.plugin_api._ws_upgrade_authorized", return_value=False):
            asyncio.run(blender_events_ws(ws))
        ws.close.assert_awaited_once_with(code=http_status.WS_1008_POLICY_VIOLATION)
        ws.accept.assert_not_awaited()

    def test_upload_enforces_size_cap_and_sanitizes_filename(self):
        """Verify /upload rejects oversized files with 413 and sanitizes valid filenames."""
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch("plugins.blender.dashboard.plugin_api._get_output_dir", return_value=Path(tmp)),
                patch.object(plugin_api, "MAX_UPLOAD_BYTES", 16),
            ):
                oversized = UploadFile(filename="huge$bad!.glb", file=io.BytesIO(b"x" * 32))
                with self.assertRaises(HTTPException) as ctx:
                    asyncio.run(upload_model(oversized))
                self.assertEqual(ctx.exception.status_code, 413)
                # Partial file must be cleaned up
                self.assertEqual(list(Path(tmp).iterdir()), [])

                valid = UploadFile(filename="my weird/../chair#1!.obj", file=io.BytesIO(b"v 0 0 0\n"))
                res = asyncio.run(upload_model(valid))
                self.assertTrue(res["success"])
                self.assertEqual(res["format"], "obj")
                self.assertTrue(res["filename"].endswith("_chair_1.obj"))


if __name__ == "__main__":
    unittest.main()
