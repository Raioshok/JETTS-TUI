"""Google Antigravity OAuth — sign in with a Google AI Pro / Ultra plan.

Antigravity is Google's agentic IDE. Its Google sign-in grants access to the
Cloud Code Assist backend (``cloudcode-pa.googleapis.com`` / ``v1internal``),
which serves Gemini 3.x and Claude models against the quota attached to the
user's Google AI subscription (Free, Pro, or Ultra).

This module owns the account side of that integration:

* browser login (OAuth 2.0 authorization code + PKCE, loopback redirect, or a
  pasted redirect URL when the browser runs on another machine),
* token refresh,
* Cloud Code project discovery / onboarding (``loadCodeAssist`` /
  ``onboardUser``) and subscription-tier detection,
* live model discovery (``fetchAvailableModels``).

Tokens are stored in the profile's ``auth.json`` under
``providers.antigravity``. The request/response translation lives in
``agent/antigravity_adapter.py``.

Antigravity is not a public API. Google's Antigravity terms restrict use of
the service to Google's own clients, and third-party access has led to
account restrictions for some users. The login flow states this and asks for
confirmation before it opens the browser.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import threading
import time
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

logger = logging.getLogger(__name__)

PROVIDER_ID = "antigravity"

# Antigravity's desktop OAuth client. Google treats installed-app client
# secrets as non-confidential (they ship inside every desktop build), so they
# are embedded the same way Gemini CLI embeds its own. Values in .env
# override them (e.g. for a self-registered OAuth client).
ANTIGRAVITY_OAUTH_CLIENT_ID = (
    "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"
)
ANTIGRAVITY_OAUTH_CLIENT_SECRET = "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"
CLIENT_ID_ENV = "ANTIGRAVITY_OAUTH_CLIENT_ID"
CLIENT_SECRET_ENV = "ANTIGRAVITY_OAUTH_CLIENT_SECRET"
ANTIGRAVITY_OAUTH_SCOPES = (
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/cclog",
    "https://www.googleapis.com/auth/experimentsandconfigs",
)
# The OAuth client only allow-lists this exact loopback redirect.
ANTIGRAVITY_REDIRECT_HOST = "localhost"
ANTIGRAVITY_REDIRECT_PORT = 51121
ANTIGRAVITY_REDIRECT_PATH = "/oauth-callback"
ANTIGRAVITY_REDIRECT_URI = (
    f"http://{ANTIGRAVITY_REDIRECT_HOST}:{ANTIGRAVITY_REDIRECT_PORT}{ANTIGRAVITY_REDIRECT_PATH}"
)
GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v1/userinfo?alt=json"

ANTIGRAVITY_ENDPOINT_DAILY = "https://daily-cloudcode-pa.sandbox.googleapis.com"
ANTIGRAVITY_ENDPOINT_AUTOPUSH = "https://autopush-cloudcode-pa.sandbox.googleapis.com"
ANTIGRAVITY_ENDPOINT_PROD = "https://cloudcode-pa.googleapis.com"
# Inference tries the daily sandbox first (where Antigravity's own client
# points); project discovery tries prod first.
ANTIGRAVITY_INFERENCE_ENDPOINTS = (
    ANTIGRAVITY_ENDPOINT_DAILY,
    ANTIGRAVITY_ENDPOINT_AUTOPUSH,
    ANTIGRAVITY_ENDPOINT_PROD,
)
ANTIGRAVITY_LOAD_ENDPOINTS = (
    ANTIGRAVITY_ENDPOINT_PROD,
    ANTIGRAVITY_ENDPOINT_DAILY,
    ANTIGRAVITY_ENDPOINT_AUTOPUSH,
)
DEFAULT_ANTIGRAVITY_BASE_URL = ANTIGRAVITY_ENDPOINT_DAILY
# Fallback project used by Antigravity when the account has no Cloud Code
# project of its own and onboarding does not return one.
ANTIGRAVITY_DEFAULT_PROJECT_ID = "rising-fact-p41fc"

ANTIGRAVITY_VERSION = "1.18.3"
ANTIGRAVITY_CLIENT_METADATA = {
    "ideType": "ANTIGRAVITY",
    "platform": "PLATFORM_UNSPECIFIED",
    "pluginType": "GEMINI",
}

ANTIGRAVITY_ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 120

# Used when live discovery (fetchAvailableModels) is unavailable. Newest
# first; the live list always wins when it answers.
DEFAULT_ANTIGRAVITY_MODELS = (
    "gemini-3.1-pro-high",
    "gemini-3.1-pro-low",
    "gemini-3-pro-high",
    "gemini-3-pro-low",
    "gemini-3-flash",
    "claude-opus-4-6-thinking",
    "claude-sonnet-4-6",
)
DEFAULT_ANTIGRAVITY_AUX_MODEL = "gemini-3-flash"

TERMS_WARNING = (
    "Antigravity is not a public API. Google's terms only permit using it\n"
    "through Google's own Antigravity client, and some users of third-party\n"
    "Antigravity integrations have reported their Google accounts being\n"
    "restricted. Use an account you are prepared to risk."
)


def _auth_error(message: str, code: str, *, relogin_required: bool = False):
    from jettstui.auth import AuthError

    return AuthError(message, provider=PROVIDER_ID, code=code, relogin_required=relogin_required)


def oauth_client_credentials() -> tuple[str, str]:
    """Return ``(client_id, client_secret)``: .env overrides, else the built-in client."""
    client_id = os.getenv(CLIENT_ID_ENV, "").strip() or ANTIGRAVITY_OAUTH_CLIENT_ID
    client_secret = os.getenv(CLIENT_SECRET_ENV, "").strip() or ANTIGRAVITY_OAUTH_CLIENT_SECRET
    return client_id, client_secret


def antigravity_headers() -> Dict[str, str]:
    """Headers the Cloud Code backend expects from an Antigravity client."""
    return {
        "User-Agent": f"antigravity/{ANTIGRAVITY_VERSION} windows/amd64",
        "X-Goog-Api-Client": "google-cloud-sdk vscode_cloudshelleditor/0.1",
        "Client-Metadata": json.dumps(ANTIGRAVITY_CLIENT_METADATA, separators=(",", ":")),
    }


# ---------------------------------------------------------------------------
# PKCE + authorize URL
# ---------------------------------------------------------------------------

def _code_verifier() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode("ascii")


def _code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def build_authorize_url(*, state: str, code_challenge: str) -> str:
    params = {
        "client_id": oauth_client_credentials()[0],
        "response_type": "code",
        "redirect_uri": ANTIGRAVITY_REDIRECT_URI,
        "scope": " ".join(ANTIGRAVITY_OAUTH_SCOPES),
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
        # offline + consent guarantees a refresh_token on every login.
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{GOOGLE_AUTHORIZE_URL}?{urlencode(params)}"


def parse_redirect_input(raw: str) -> Dict[str, Optional[str]]:
    """Extract ``code``/``state``/``error`` from a pasted redirect URL or bare code."""
    text = (raw or "").strip()
    if not text:
        return {"code": None, "state": None, "error": None}
    if "://" not in text and "?" not in text and "=" not in text:
        return {"code": text, "state": None, "error": None}
    query = urlparse(text).query if "://" in text else text.lstrip("?")
    params = parse_qs(query)
    return {
        "code": (params.get("code") or [None])[0],
        "state": (params.get("state") or [None])[0],
        "error": (params.get("error") or [None])[0],
    }


# ---------------------------------------------------------------------------
# Loopback callback
# ---------------------------------------------------------------------------

def _wait_for_loopback_callback(
    timeout_seconds: float,
    *,
    should_stop: Optional[Any] = None,
) -> Dict[str, Optional[str]]:
    """Serve the registered redirect URI until Google calls back.

    ``should_stop`` (optional callable) lets a caller abandon the wait — the
    desktop flow stops listening once the user pastes the redirect URL or
    cancels.
    """
    result: Dict[str, Optional[str]] = {"code": None, "state": None, "error": None}

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != ANTIGRAVITY_REDIRECT_PATH:
                self.send_response(404)
                self.end_headers()
                return
            params = parse_qs(parsed.query)
            result["code"] = (params.get("code") or [None])[0]
            result["state"] = (params.get("state") or [None])[0]
            result["error"] = (params.get("error") or [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            heading = "Sign-in failed." if result["error"] else "Signed in to Antigravity."
            self.wfile.write(
                f"<html><body><h1>{heading}</h1>You can close this tab and return to JettsTUI.</body></html>".encode("utf-8")
            )

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

    class _ReuseHTTPServer(HTTPServer):
        allow_reuse_address = True

    try:
        server = _ReuseHTTPServer(("127.0.0.1", ANTIGRAVITY_REDIRECT_PORT), _Handler)
    except OSError as exc:
        raise _auth_error(
            f"Could not listen on {ANTIGRAVITY_REDIRECT_URI} ({exc}). "
            "Close whatever is using port 51121 (for example the Antigravity app) and retry.",
            "antigravity_callback_bind_failed",
        ) from exc

    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
    thread.start()
    deadline = time.monotonic() + max(5.0, timeout_seconds)
    try:
        while time.monotonic() < deadline:
            if result["code"] or result["error"]:
                return result
            if should_stop is not None and should_stop():
                return result
            time.sleep(0.1)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1.0)
    raise _auth_error(
        "Timed out waiting for the Google sign-in redirect.",
        "antigravity_callback_timeout",
    )


# ---------------------------------------------------------------------------
# Token exchange / refresh
# ---------------------------------------------------------------------------

def _token_request(data: Dict[str, str], *, timeout_seconds: float, failure_code: str) -> Dict[str, Any]:
    client_id, client_secret = oauth_client_credentials()
    try:
        response = httpx.post(
            GOOGLE_TOKEN_URL,
            data={**data, "client_id": client_id, "client_secret": client_secret},
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            timeout=timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise _auth_error(f"Google token request failed: {exc}", failure_code) from exc
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if response.status_code != 200 or not isinstance(payload, dict) or not payload.get("access_token"):
        error = payload.get("error") if isinstance(payload, dict) else None
        description = (payload.get("error_description") if isinstance(payload, dict) else None) or response.text[:300]
        relogin = error in {"invalid_grant", "unauthorized_client"}
        raise _auth_error(
            f"Google token request failed (HTTP {response.status_code}): {description or error or 'unknown error'}"
            + (" — run `jettstui auth add antigravity` to sign in again." if relogin else ""),
            failure_code,
            relogin_required=relogin,
        )
    return payload


def _expires_at_ms(payload: Dict[str, Any]) -> int:
    try:
        expires_in = int(payload.get("expires_in") or 3600)
    except (TypeError, ValueError):
        expires_in = 3600
    return int((time.time() + max(60, expires_in)) * 1000)


def exchange_code_for_tokens(code: str, code_verifier: str, *, timeout_seconds: float = 20.0) -> Dict[str, Any]:
    payload = _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": ANTIGRAVITY_REDIRECT_URI,
            "code_verifier": code_verifier,
        },
        timeout_seconds=timeout_seconds,
        failure_code="antigravity_token_exchange_failed",
    )
    if not payload.get("refresh_token"):
        raise _auth_error(
            "Google did not return a refresh token. Revoke JettsTUI/Antigravity access at "
            "https://myaccount.google.com/permissions and sign in again.",
            "antigravity_refresh_token_missing",
        )
    return payload


def refresh_access_token(refresh_token: str, *, timeout_seconds: float = 20.0) -> Dict[str, Any]:
    return _token_request(
        {"grant_type": "refresh_token", "refresh_token": refresh_token},
        timeout_seconds=timeout_seconds,
        failure_code="antigravity_refresh_failed",
    )


def fetch_user_email(access_token: str, *, timeout_seconds: float = 15.0) -> str:
    try:
        response = httpx.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=timeout_seconds,
        )
        if response.status_code == 200:
            return str(response.json().get("email") or "")
    except (httpx.HTTPError, ValueError) as exc:
        logger.debug("Antigravity userinfo lookup failed: %s", exc)
    return ""


# ---------------------------------------------------------------------------
# Cloud Code project discovery + tier
# ---------------------------------------------------------------------------

def _post_v1internal(
    client: httpx.Client,
    endpoint: str,
    method: str,
    access_token: str,
    body: Dict[str, Any],
) -> httpx.Response:
    return client.post(
        f"{endpoint}/v1internal:{method}",
        json=body,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            **antigravity_headers(),
        },
    )


def _project_id_from(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return str(value.get("id") or "").strip()
    return ""


def describe_tier(tier_id: str) -> str:
    """Map a Cloud Code tier id onto the Google AI plan the user recognises."""
    tid = (tier_id or "").lower()
    if "ultra" in tid:
        return "Google AI Ultra"
    if "pro" in tid:
        return "Google AI Pro"
    if tid in {"free-tier", "free"} or "free" in tid:
        return "Free"
    if tid in {"standard-tier", "legacy-tier"}:
        return "Standard"
    return tier_id or "unknown"


def discover_project(access_token: str, *, timeout_seconds: float = 30.0) -> Dict[str, str]:
    """Return ``{"project_id", "tier_id"}`` for the signed-in account.

    Calls ``loadCodeAssist``; when the account has no Cloud Code project yet,
    runs ``onboardUser`` on its default tier and polls the long-running
    operation. Falls back to Antigravity's shared default project.
    """
    metadata = dict(ANTIGRAVITY_CLIENT_METADATA)
    last_error = ""
    with httpx.Client(timeout=timeout_seconds) as client:
        for endpoint in ANTIGRAVITY_LOAD_ENDPOINTS:
            try:
                response = _post_v1internal(client, endpoint, "loadCodeAssist", access_token, {"metadata": metadata})
            except httpx.HTTPError as exc:
                last_error = str(exc)
                continue
            if response.status_code != 200:
                last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                continue
            try:
                payload = response.json()
            except ValueError:
                last_error = "invalid JSON from loadCodeAssist"
                continue

            paid_tier = payload.get("paidTier") if isinstance(payload.get("paidTier"), dict) else {}
            current_tier = payload.get("currentTier") if isinstance(payload.get("currentTier"), dict) else {}
            tier_id = str(paid_tier.get("id") or current_tier.get("id") or "")
            project_id = _project_id_from(payload.get("cloudaicompanionProject"))
            if project_id:
                return {"project_id": project_id, "tier_id": tier_id}

            onboard_tier = tier_id
            if not onboard_tier:
                for tier in payload.get("allowedTiers") or []:
                    if isinstance(tier, dict) and tier.get("isDefault"):
                        onboard_tier = str(tier.get("id") or "")
                        break
            project_id = _onboard_user(client, endpoint, access_token, onboard_tier or "free-tier", metadata)
            if project_id:
                return {"project_id": project_id, "tier_id": tier_id or onboard_tier}
            break

    logger.info("Antigravity project discovery fell back to the default project (%s)", last_error or "no project")
    return {"project_id": ANTIGRAVITY_DEFAULT_PROJECT_ID, "tier_id": ""}


def _onboard_user(
    client: httpx.Client,
    endpoint: str,
    access_token: str,
    tier_id: str,
    metadata: Dict[str, Any],
    *,
    attempts: int = 10,
    poll_seconds: float = 3.0,
) -> str:
    body = {"tierId": tier_id, "metadata": metadata}
    for _ in range(max(1, attempts)):
        try:
            response = _post_v1internal(client, endpoint, "onboardUser", access_token, body)
        except httpx.HTTPError as exc:
            logger.debug("Antigravity onboardUser failed: %s", exc)
            return ""
        if response.status_code != 200:
            logger.debug("Antigravity onboardUser HTTP %s: %s", response.status_code, response.text[:200])
            return ""
        try:
            operation = response.json()
        except ValueError:
            return ""
        if operation.get("done"):
            result = operation.get("response") if isinstance(operation.get("response"), dict) else {}
            return _project_id_from(result.get("cloudaicompanionProject"))
        time.sleep(poll_seconds)
    return ""


def _fetch_model_entries(
    access_token: str,
    project_id: str,
    *,
    timeout_seconds: float = 15.0,
) -> Dict[str, Dict[str, Any]]:
    """Return ``{model_id: metadata}`` from ``fetchAvailableModels`` (``{}`` on failure).

    Internal routing / tab-completion / image models are dropped: they are
    not chat models.
    """
    with httpx.Client(timeout=timeout_seconds) as client:
        for endpoint in ANTIGRAVITY_INFERENCE_ENDPOINTS:
            try:
                response = _post_v1internal(
                    client, endpoint, "fetchAvailableModels", access_token, {"project": project_id}
                )
            except httpx.HTTPError:
                continue
            if response.status_code != 200:
                continue
            try:
                models = response.json().get("models")
            except ValueError:
                continue
            entries: Dict[str, Dict[str, Any]] = {}
            if isinstance(models, dict):
                for name, meta in models.items():
                    entries[str(name)] = meta if isinstance(meta, dict) else {}
            elif isinstance(models, list):
                for item in models:
                    if isinstance(item, dict):
                        entries[str(item.get("name") or item.get("id") or "")] = item
                    else:
                        entries[str(item)] = {}
            entries = {
                name: meta for name, meta in entries.items()
                if name and not name.startswith(("chat_", "tab_")) and "image" not in name
            }
            if entries:
                return entries
    return {}


def fetch_available_models(
    access_token: str,
    project_id: str,
    *,
    timeout_seconds: float = 15.0,
) -> List[str]:
    """Return the model ids the account can use, or ``[]`` when discovery fails."""
    entries = _fetch_model_entries(access_token, project_id, timeout_seconds=timeout_seconds)
    return sorted(entries, key=_model_sort_key)


def fetch_model_quotas(
    access_token: str,
    project_id: str,
    *,
    timeout_seconds: float = 15.0,
) -> List[Dict[str, Any]]:
    """Per-model quota: ``[{model, label, remaining_fraction, reset_time}]``.

    Models the backend reports without quota information are omitted.
    """
    quotas: List[Dict[str, Any]] = []
    entries = _fetch_model_entries(access_token, project_id, timeout_seconds=timeout_seconds)
    for name in sorted(entries, key=_model_sort_key):
        meta = entries[name]
        info = meta.get("quotaInfo") if isinstance(meta.get("quotaInfo"), dict) else {}
        remaining = info.get("remainingFraction")
        if not isinstance(remaining, (int, float)):
            continue
        quotas.append({
            "model": name,
            "label": str(meta.get("displayName") or name),
            "remaining_fraction": max(0.0, min(1.0, float(remaining))),
            "reset_time": info.get("resetTime"),
        })
    return quotas


def _model_sort_key(name: str) -> tuple:
    if name in DEFAULT_ANTIGRAVITY_MODELS:
        return (0, DEFAULT_ANTIGRAVITY_MODELS.index(name), name)
    return (1, 0, name)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _load_state() -> Optional[Dict[str, Any]]:
    from jettstui.auth import _load_auth_store, _load_provider_state

    state = _load_provider_state(_load_auth_store(), PROVIDER_ID)
    return dict(state) if isinstance(state, dict) else None


def _save_state(state: Dict[str, Any], *, set_active: bool) -> None:
    from jettstui.auth import _auth_store_lock, _load_auth_store, _save_auth_store, _store_provider_state

    with _auth_store_lock():
        auth_store = _load_auth_store()
        _store_provider_state(auth_store, PROVIDER_ID, state, set_active=set_active)
        _save_auth_store(auth_store)


def _access_token_is_expiring(state: Dict[str, Any], skew_seconds: int) -> bool:
    try:
        expires_at_ms = int(state.get("expires_at_ms") or 0)
    except (TypeError, ValueError):
        return True
    return expires_at_ms <= int((time.time() + max(0, skew_seconds)) * 1000)


def resolve_antigravity_runtime_credentials(
    *,
    refresh_if_expiring: bool = True,
    force_refresh: bool = False,
    refresh_skew_seconds: int = ANTIGRAVITY_ACCESS_TOKEN_REFRESH_SKEW_SECONDS,
) -> Dict[str, Any]:
    """Return a usable access token + project id, refreshing when needed."""
    from jettstui.auth import _auth_store_lock

    state = _load_state()
    if not state or not state.get("refresh_token"):
        raise _auth_error(
            "Not signed in to Antigravity. Run `jettstui auth add antigravity` "
            "(or pick Google Antigravity in `jettstui model`).",
            "antigravity_auth_missing",
            relogin_required=True,
        )

    needs_refresh = force_refresh or not state.get("access_token") or (
        refresh_if_expiring and _access_token_is_expiring(state, refresh_skew_seconds)
    )
    if needs_refresh:
        # Re-read under the lock so concurrent processes refresh once.
        with _auth_store_lock():
            current = _load_state() or state
            if force_refresh or not current.get("access_token") or _access_token_is_expiring(current, refresh_skew_seconds):
                payload = refresh_access_token(str(current.get("refresh_token") or ""))
                current["access_token"] = str(payload["access_token"])
                current["expires_at_ms"] = _expires_at_ms(payload)
                if payload.get("refresh_token"):
                    current["refresh_token"] = str(payload["refresh_token"])
                current["last_refresh"] = datetime.now(timezone.utc).isoformat()
                _save_state(current, set_active=False)
            state = current

    project_id = str(state.get("project_id") or "").strip()
    if not project_id:
        discovered = discover_project(str(state["access_token"]))
        project_id = discovered["project_id"]
        state["project_id"] = project_id
        state["tier_id"] = discovered.get("tier_id") or state.get("tier_id") or ""
        _save_state(state, set_active=False)

    return {
        "provider": PROVIDER_ID,
        "api_key": str(state["access_token"]),
        "base_url": str(state.get("base_url") or DEFAULT_ANTIGRAVITY_BASE_URL).rstrip("/"),
        "project_id": project_id,
        "email": state.get("email") or "",
        "tier_id": state.get("tier_id") or "",
        "expires_at_ms": state.get("expires_at_ms"),
        "last_refresh": state.get("last_refresh"),
        "source": "jettstui-auth-store",
    }


def get_antigravity_auth_status() -> Dict[str, Any]:
    state = _load_state()
    if not state or not state.get("refresh_token"):
        return {"logged_in": False, "provider": PROVIDER_ID}
    tier_id = str(state.get("tier_id") or "")
    return {
        "logged_in": True,
        "provider": PROVIDER_ID,
        "email": state.get("email") or "",
        "project_id": state.get("project_id") or "",
        "tier_id": tier_id,
        "plan": describe_tier(tier_id),
        "expires_at_ms": state.get("expires_at_ms"),
        "last_refresh": state.get("last_refresh"),
    }


# ---------------------------------------------------------------------------
# Interactive login
# ---------------------------------------------------------------------------

def login_antigravity(
    *,
    open_browser: bool = True,
    timeout_seconds: float = 300.0,
    manual: Optional[bool] = None,
    set_active: bool = True,
    confirm_terms: bool = True,
) -> Dict[str, Any]:
    """Run the browser sign-in and persist the resulting credentials.

    ``manual`` forces the paste-the-redirect-URL flow (default: on for SSH /
    browser-less remote sessions, where the loopback redirect cannot reach the
    machine running JettsTUI).
    """
    from jettstui.auth import _can_open_graphical_browser, _is_remote_session

    oauth_client_credentials()
    print()
    print("Sign in to Google Antigravity (Google AI Pro / Ultra plans)")
    print()
    print(TERMS_WARNING)
    print()
    if confirm_terms:
        try:
            answer = input("Continue? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer not in {"y", "yes"}:
            raise _auth_error("Antigravity sign-in cancelled.", "antigravity_login_cancelled")

    if manual is None:
        manual = _is_remote_session()

    verifier = _code_verifier()
    state_nonce = secrets.token_urlsafe(24)
    authorize_url = build_authorize_url(state=state_nonce, code_challenge=_code_challenge(verifier))

    print()
    print("Open this URL to sign in with your Google account:")
    print(authorize_url)
    print()

    if manual:
        print("After approving, your browser is redirected to a localhost page that")
        print("will not load. Copy the full URL from the address bar and paste it here.")
        try:
            pasted = input("Redirect URL: ")
        except (EOFError, KeyboardInterrupt):
            pasted = ""
        callback = parse_redirect_input(pasted)
    else:
        if open_browser and _can_open_graphical_browser():
            try:
                webbrowser.open(authorize_url)
                print("Browser opened — waiting for Google sign-in...")
            except Exception:
                print("Could not open a browser automatically; use the URL above.")
        else:
            print("Waiting for Google sign-in...")
        callback = _wait_for_loopback_callback(timeout_seconds)

    if callback.get("error"):
        raise _auth_error(f"Google sign-in failed: {callback['error']}", "antigravity_authorize_failed")
    if not callback.get("code"):
        raise _auth_error("No authorization code received.", "antigravity_code_missing")
    if callback.get("state") and callback["state"] != state_nonce:
        raise _auth_error("Google sign-in failed: state mismatch.", "antigravity_state_mismatch")

    print("Signed in. Looking up your Antigravity project and plan...")
    return complete_login(str(callback["code"]), verifier, set_active=set_active)


def start_login() -> Dict[str, str]:
    """Begin a sign-in: return ``{auth_url, verifier, state}`` for a UI to drive."""
    verifier = _code_verifier()
    state_nonce = secrets.token_urlsafe(24)
    return {
        "auth_url": build_authorize_url(state=state_nonce, code_challenge=_code_challenge(verifier)),
        "verifier": verifier,
        "state": state_nonce,
    }


def complete_login(code: str, verifier: str, *, set_active: bool = True) -> Dict[str, Any]:
    """Exchange an authorization code, discover the project, persist the account."""
    tokens = exchange_code_for_tokens(code, verifier)
    access_token = str(tokens["access_token"])
    email = fetch_user_email(access_token)
    discovered = discover_project(access_token)

    state = {
        "auth_type": "oauth_pkce",
        "access_token": access_token,
        "refresh_token": str(tokens["refresh_token"]),
        "expires_at_ms": _expires_at_ms(tokens),
        "email": email,
        "project_id": discovered["project_id"],
        "tier_id": discovered.get("tier_id") or "",
        "base_url": DEFAULT_ANTIGRAVITY_BASE_URL,
        "last_refresh": datetime.now(timezone.utc).isoformat(),
    }
    _save_state(state, set_active=set_active)
    return state
