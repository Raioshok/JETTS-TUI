"""Freebuff OAuth and 1-hour free model session admission integration.

Provides:
- Device-code OAuth login flow for freebuff.com accounts
- 1-hour free session admission lifecycle (POST /api/v1/freebuff/session/admission)
- Session status and quota tracking (GET /api/v1/freebuff/session)
- Multi-account token storage and credential resolution
"""

from __future__ import annotations

import logging
import os
import time
import uuid
import webbrowser
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_FREEBUFF_PORTAL_URL = "https://freebuff.com"
DEFAULT_FREEBUFF_INFERENCE_URL = "https://codebuff.com/api/v1"
FREEBUFF_SESSION_DURATION_SECONDS = 3600  # 1 hour free model usage


class FreebuffAuthError(RuntimeError):
    """Raised when Freebuff OAuth or session admission fails."""

    def __init__(self, message: str, *, status_code: int | None = None, code: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def request_freebuff_device_code(
    client: httpx.Client,
    portal_base_url: str = DEFAULT_FREEBUFF_PORTAL_URL,
    fingerprint_id: str | None = None,
) -> Dict[str, Any]:
    """Request a device login code from Freebuff.

    Calls POST {portal_base_url}/api/auth/cli/code with a unique client fingerprint.
    Returns:
        {
            "fingerprintId": str,
            "fingerprintHash": str,
            "loginUrl": str,
            "expiresAt": int,
            "expiresInMs": int,
        }
    """
    if not fingerprint_id:
        fingerprint_id = f"jettstui-cli-{uuid.uuid4().hex[:16]}"

    url = f"{portal_base_url.rstrip('/')}/api/auth/cli/code"
    try:
        resp = client.post(
            url,
            json={"fingerprintId": fingerprint_id},
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
    except Exception as exc:
        raise FreebuffAuthError(
            f"Failed to connect to Freebuff login service at {url}: {exc}",
            code="network_error",
        ) from exc

    if resp.status_code != 200:
        raise FreebuffAuthError(
            f"Freebuff login code request failed (HTTP {resp.status_code}): {resp.text[:200]}",
            status_code=resp.status_code,
            code="code_request_failed",
        )

    try:
        data = resp.json()
    except Exception as exc:
        raise FreebuffAuthError(
            f"Invalid JSON response from Freebuff login service: {resp.text[:200]}",
            code="invalid_json",
        ) from exc

    if not data.get("loginUrl"):
        raise FreebuffAuthError("Freebuff login response missing 'loginUrl'", code="missing_url")

    return data


def poll_freebuff_login_status(
    client: httpx.Client,
    *,
    fingerprint_id: str,
    fingerprint_hash: str,
    expires_at: int,
    portal_base_url: str = DEFAULT_FREEBUFF_PORTAL_URL,
    interval_seconds: float = 3.0,
    timeout_seconds: float = 300.0,
) -> Dict[str, Any]:
    """Poll Freebuff for user authorization.

    Calls GET {portal_base_url}/api/auth/cli/status until the user signs in or timeout occurs.
    """
    start_time = time.time()
    url = f"{portal_base_url.rstrip('/')}/api/auth/cli/status"
    params = {
        "fingerprintId": fingerprint_id,
        "fingerprintHash": fingerprint_hash,
        "expiresAt": str(expires_at),
    }

    while True:
        if (time.time() - start_time) >= timeout_seconds:
            raise FreebuffAuthError("Freebuff login polling timed out.", code="timeout")

        try:
            resp = client.get(url, params=params, headers={"Accept": "application/json"})
        except Exception as exc:
            logger.debug("Freebuff login polling network error: %s", exc)
            time.sleep(interval_seconds)
            continue

        if resp.status_code == 200:
            try:
                data = resp.json()
            except Exception:
                data = {}
            user = data.get("user")
            if isinstance(user, dict) and user.get("authToken"):
                return user
        elif resp.status_code not in (401, 403, 404):
            logger.debug("Freebuff login polling returned status %d", resp.status_code)

        time.sleep(interval_seconds)


def run_freebuff_oauth_login(
    *,
    portal_base_url: str = DEFAULT_FREEBUFF_PORTAL_URL,
    open_browser: bool = True,
    timeout_seconds: float = 300.0,
) -> Dict[str, Any]:
    """Run full Freebuff OAuth flow: request code, open browser, poll, return credentials."""
    print("Starting Freebuff OAuth login...")
    timeout = httpx.Timeout(max(20.0, min(timeout_seconds, 60.0)))
    with httpx.Client(timeout=timeout) as client:
        code_data = request_freebuff_device_code(client, portal_base_url=portal_base_url)
        login_url = code_data["loginUrl"]
        print()
        print("To sign in to your Freebuff account and unlock 1 hour of free model access:")
        print(f"  1. Open: {login_url}")
        print("  2. Sign in with GitHub or Google")
        if open_browser:
            try:
                opened = webbrowser.open(login_url)
                if opened:
                    print("  (Opened login page in your default browser)")
                else:
                    print("  Please copy and paste the URL above into your browser.")
            except Exception:
                print("  Please copy and paste the URL above into your browser.")

        print("Waiting for login approval...")
        user = poll_freebuff_login_status(
            client,
            fingerprint_id=code_data["fingerprintId"],
            fingerprint_hash=code_data["fingerprintHash"],
            expires_at=code_data["expiresAt"],
            portal_base_url=portal_base_url,
            timeout_seconds=timeout_seconds,
        )

    auth_token = user["authToken"]
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    print("\n✓ Freebuff OAuth login successful!")
    if user.get("email"):
        print(f"  Logged in as: {user['email']}")

    return {
        "tokens": {
            "access_token": auth_token,
            "token_type": "Bearer",
        },
        "user": user,
        "base_url": DEFAULT_FREEBUFF_INFERENCE_URL,
        "last_refresh": now_iso,
        "source": "oauth-device-code",
    }


# =============================================================================
# 1-Hour Free Session Admission
# =============================================================================

_ACTIVE_FREEBUFF_SESSIONS: dict[str, dict[str, Any]] = {}


def admit_freebuff_session(
    auth_token: str,
    model: str = "deepseek/deepseek-v4-pro",
    *,
    instance_id: str | None = None,
    inference_origin: str = "https://codebuff.com",
    timeout_seconds: float = 15.0,
) -> Dict[str, Any]:
    """Admit/start a 1-hour free model session on Freebuff.

    Calls POST {inference_origin}/api/v1/freebuff/session/admission
    Headers:
      - Authorization: Bearer <authToken>
      - x-freebuff-model: <model>
      - x-freebuff-instance-id: <instanceId>
      - x-freebuff-wallet-spend-limit: session
      - x-freebuff-multi-session: 1
      - x-freebuff-catalog-protocol: 1
    """
    if not instance_id:
        instance_id = str(uuid.uuid4())

    url = f"{inference_origin.rstrip('/')}/api/v1/freebuff/session/admission"
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "x-freebuff-model": model,
        "x-freebuff-instance-id": instance_id,
        "x-freebuff-wallet-spend-limit": "session",
        "x-freebuff-multi-session": "1",
        "x-freebuff-catalog-protocol": "1",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    with httpx.Client(timeout=httpx.Timeout(timeout_seconds)) as client:
        try:
            resp = client.post(url, headers=headers)
        except Exception as exc:
            raise FreebuffAuthError(f"Failed to connect to Freebuff session admission: {exc}") from exc

    if resp.status_code == 200:
        try:
            data = resp.json()
        except Exception:
            data = {"status": "active"}
        session_info = {
            "status": data.get("status", "active"),
            "instance_id": instance_id,
            "model": model,
            "admitted_at": time.time(),
            "expires_at": time.time() + FREEBUFF_SESSION_DURATION_SECONDS,
            "raw": data,
        }
        _ACTIVE_FREEBUFF_SESSIONS[auth_token] = session_info
        return session_info

    error_text = resp.text[:250]
    raise FreebuffAuthError(
        f"Freebuff 1h free session admission failed (HTTP {resp.status_code}): {error_text}",
        status_code=resp.status_code,
    )


def get_or_create_freebuff_session(
    auth_token: str,
    model: str = "deepseek/deepseek-v4-pro",
    *,
    inference_origin: str = "https://codebuff.com",
) -> Dict[str, Any]:
    """Ensure an active 1-hour free session exists for the given auth token and model.

    If an active session exists and has not expired, returns it.
    Otherwise, starts/resumes a 1-hour session via admission.
    """
    cached = _ACTIVE_FREEBUFF_SESSIONS.get(auth_token)
    now = time.time()
    if cached and cached.get("expires_at", 0) > (now + 60) and cached.get("model") == model:
        return cached

    # Admit new 1-hour session
    return admit_freebuff_session(auth_token, model, inference_origin=inference_origin)
