"""Removed hosted scheduler endpoints must stay absent from both HTTP surfaces."""

from fastapi.testclient import TestClient

from jettstui.dashboard_auth.public_paths import PUBLIC_API_PATHS
from jettstui.web_server import app
from gateway.config import PlatformConfig
from gateway.platforms.api_server import APIServerAdapter
from plugins.cron_providers import discover_cron_schedulers


def test_dashboard_has_no_public_cron_fire_endpoint():
    assert "/api/cron/fire" not in PUBLIC_API_PATHS
    assert "/api/cron/fire" not in {route.path for route in app.routes}
    # The auth middleware rejects this former public path before routing.
    assert TestClient(app).post("/api/cron/fire", json={"job_id": "x"}).status_code == 401


def test_gateway_has_no_hosted_cron_fire_endpoint():
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={"key": "sk-secret"}))
    assert "/api/cron/fire" not in {path for _, path, _ in adapter._http_route_table()}


def test_hosted_scheduler_is_not_bundled():
    assert all(name != "chronos" for name, _, _ in discover_cron_schedulers())
