"""Harness: dashboard opt-in via FREEIDE_DASHBOARD.

Today (tini): dashboard starts once when FREEIDE_DASHBOARD=1; if it crashes
it stays dead. After Phase 2 (s6): dashboard starts once; if it crashes
it is restarted under supervision. The restart-after-crash test lives in
Phase 2 Task 2.5; this file only locks the opt-in surface (which must
not change between tini and s6).

Every ``docker exec`` here runs as the unprivileged ``jettstui`` user
(via :func:`docker_exec`/:func:`docker_exec_sh` in conftest), matching
the realistic runtime context. See the conftest module docstring.
"""
from __future__ import annotations

import json
import time

from tests.docker.conftest import docker_exec, docker_exec_sh, start_container, poll_container


def test_dashboard_not_running_by_default(
    built_image: str, container_name: str,
) -> None:
    """Without FREEIDE_DASHBOARD, no dashboard process should be running."""
    start_container(built_image, container_name, cmd="sleep 60")
    r = docker_exec(container_name, "pgrep", "-f", "jetts-tui dashboard")
    # pgrep exits non-zero when no match found
    assert r.returncode != 0, (
        "Dashboard should not be running without FREEIDE_DASHBOARD"
    )


def test_dashboard_slot_reports_down_when_disabled(
    built_image: str, container_name: str,
) -> None:
    """Without FREEIDE_DASHBOARD, s6-svstat should report the dashboard
    slot as DOWN (not up-with-sleep-infinity, which would
    false-positive `jetts-tui doctor` and any other health check).

    Locks the PR #30136 review item I3 fix: cont-init.d/03-dashboard-toggle
    writes a `down` marker file in the live service-dir when
    FREEIDE_DASHBOARD is unset, so the slot reflects reality.
    """
    start_container(built_image, container_name, cmd="sleep 60")
    # /command/ isn't on PATH for docker-exec sessions, so call by
    # absolute path.
    r = docker_exec(
        container_name, "/command/s6-svstat", "/run/service/dashboard",
    )
    assert r.returncode == 0, f"s6-svstat failed: {r.stderr!r} / {r.stdout!r}"
    assert "down" in r.stdout, (
        f"Dashboard slot should be 'down' without FREEIDE_DASHBOARD; "
        f"svstat reports: {r.stdout!r}"
    )


def test_dashboard_slot_reports_up_when_enabled(
    built_image: str, container_name: str,
) -> None:
    """Symmetry: with FREEIDE_DASHBOARD=1, s6-svstat reports the slot as up."""
    # The default dashboard host is 0.0.0.0, which now engages the
    # OAuth auth gate. Without a provider registered (no
    # FREEIDE_DASHBOARD_OAUTH_CLIENT_ID in this test env), start_server
    # would fail closed and the slot would never come up. Pin the
    # explicit insecure opt-in to keep this test focused on the s6
    # supervision contract, not the auth gate.
    start_container(
        built_image, container_name,
        "FREEIDE_DASHBOARD=1",
        "FREEIDE_DASHBOARD_BASIC_AUTH_USERNAME=admin",
        "FREEIDE_DASHBOARD_BASIC_AUTH_PASSWORD=test-dashboard-pw",
        cmd="sleep 120",
    )
    # uvicorn takes a moment to bind; poll svstat.
    poll_container(container_name, "/command/s6-svstat /run/service/dashboard | grep -q 'up '")


def test_dashboard_opt_in_starts(
    built_image: str, container_name: str,
) -> None:
    """With FREEIDE_DASHBOARD=1, a dashboard process should be visible."""
    # Default bind is 0.0.0.0, which engages the auth gate. Register the
    # bundled basic password provider so the gate has a provider and the
    # dashboard binds (vs fail-closed). Keeps the test focused on s6
    # supervision, not auth.
    start_container(
        built_image, container_name,
        "FREEIDE_DASHBOARD=1",
        "FREEIDE_DASHBOARD_BASIC_AUTH_USERNAME=admin",
        "FREEIDE_DASHBOARD_BASIC_AUTH_PASSWORD=test-dashboard-pw",
        cmd="sleep 120",
    )
    # Poll for the dashboard subprocess to appear — the entrypoint
    # backgrounds it and bootstrap (skills sync etc.) can take a few
    # seconds before the python process actually launches.
    ok, _ = poll_container(
        container_name, "pgrep -f 'jetts-tui dashboard'", deadline_s=30.0,
    )
    assert ok, "Dashboard should be running with FREEIDE_DASHBOARD=1"


def test_dashboard_port_override(
    built_image: str, container_name: str,
) -> None:
    """FREEIDE_DASHBOARD_PORT changes the dashboard's listen port."""
    # Default bind is 0.0.0.0; register the basic password provider so
    # the auth gate has a provider and the dashboard binds. See
    # test_dashboard_slot_reports_up_when_enabled for the full rationale.
    start_container(
        built_image, container_name,
        "FREEIDE_DASHBOARD=1",
        "FREEIDE_DASHBOARD_PORT=9120",
        "FREEIDE_DASHBOARD_BASIC_AUTH_USERNAME=admin",
        "FREEIDE_DASHBOARD_BASIC_AUTH_PASSWORD=test-dashboard-pw",
        cmd="sleep 120",
    )
    # The dashboard process appearing in pgrep doesn't mean it's bound
    # to the port yet — uvicorn takes another second or two to come up.
    # The image doesn't ship ss/netstat, so probe /proc/net/tcp directly:
    # port 9120 = 0x23A0, state 0A = LISTEN.
    ok, stdout = poll_container(
        container_name,
        "grep -E ' 0+:23A0 .* 0A ' /proc/net/tcp /proc/net/tcp6 "
        "2>/dev/null",
        deadline_s=60.0,
    )
    assert ok, f"Dashboard not listening on port 9120: stdout={stdout!r}"


def test_dashboard_restarts_after_crash(
    built_image: str, container_name: str,
) -> None:
    """Phase 2 invariant: under s6 supervision, killing the dashboard
    process should be recovered automatically.

    Pre-s6 (tini) behavior was "stays dead" — the test wouldn't have
    passed against that image. After the s6-overlay migration the
    dashboard runs as a longrun s6-rc service and s6-supervise restarts
    it after a ~1s backoff (the default).
    """
    # Default bind is 0.0.0.0; register the basic password provider so
    # the auth gate has a provider and the supervised dashboard binds.
    # See test_dashboard_slot_reports_up_when_enabled for the full
    # rationale.
    start_container(
        built_image, container_name,
        "FREEIDE_DASHBOARD=1",
        "FREEIDE_DASHBOARD_BASIC_AUTH_USERNAME=admin",
        "FREEIDE_DASHBOARD_BASIC_AUTH_PASSWORD=test-dashboard-pw",
        cmd="sleep 120",
    )
    # Wait for the first dashboard to come up.
    ok, _ = poll_container(
        container_name, "pgrep -f 'jetts-tui dashboard'", deadline_s=30.0,
    )
    assert ok, "Dashboard never started initially"

    # Grab the initial PID. s6 may briefly transition through restart
    # state between our poll-success and the follow-up pgrep, so retry
    # a couple of times before giving up.
    first_pid: str | None = None
    for _attempt in range(10):
        first_pid_result = docker_exec(
            container_name, "pgrep", "-f", "jetts-tui dashboard",
        )
        first_pids = first_pid_result.stdout.strip().split()
        if first_pids:
            first_pid = first_pids[0]
            break
        time.sleep(0.5)
    assert first_pid is not None, "Could not capture initial dashboard PID"

    # Kill the dashboard. The dashboard process runs as jettstui, so the
    # jettstui user can kill it (same UID).
    docker_exec(container_name, "kill", "-9", first_pid)

    # s6 backs off ~1s before restart; allow up to 15s for the new
    # process to appear with a different PID.
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        r = docker_exec(container_name, "pgrep", "-f", "jetts-tui dashboard")
        pids = r.stdout.strip().split() if r.returncode == 0 else []
        if pids and pids[0] != first_pid:
            return  # success
        time.sleep(0.5)

    raise AssertionError(
        f"Dashboard not restarted after kill (first_pid={first_pid})"
    )


# ---------------------------------------------------------------------------
# OAuth auth-gate behaviour — regression guard for the dashboard-insecure
# auto-injection bug. Pre-fix, the s6 run script appended `--insecure`
# whenever `FREEIDE_DASHBOARD_HOST` was non-loopback, silently disabling
# the OAuth gate on every container-deployed dashboard. The matching
# static-text guard lives in tests/test_docker_home_override_scripts.py;
# this is the behavioural end-to-end check.
# ---------------------------------------------------------------------------


def _http_probe(
    container: str,
    path: str,
    *,
    deadline_s: float = 60.0,
) -> tuple[int, str]:
    """Poll ``http://127.0.0.1:9119<path>`` from inside the container.

    Returns ``(status_code, body)`` as soon as the dashboard answers any
    HTTP response — 200, 401, 503, anything. The image doesn't ship
    ``curl`` but the venv's stdlib ``urllib`` is good enough; we use a
    proper ``try``/``except`` to intercept ``HTTPError`` because
    ``urlopen`` raises on 4xx/5xx, and we treat those as legitimate
    responses (the OAuth gate's 401 IS the success signal for the
    gate-engaged test).

    Connection errors (uvicorn still starting, fail-closed exited) keep
    the poll loop running until ``deadline_s`` elapses.

    The probe Python program is fed over stdin (``python -``) rather
    than ``python -c`` so we can use proper multi-line syntax with
    ``try``/``except`` blocks without escaping hell.

    Raises ``AssertionError`` on timeout.
    """
    py_program = f"""\
import urllib.request, urllib.error
req = urllib.request.Request("http://127.0.0.1:9119{path}")
try:
    r = urllib.request.urlopen(req, timeout=5)
    print(r.status)
    print(r.read().decode(), end="")
except urllib.error.HTTPError as h:
    print(h.code)
    print(h.read().decode(), end="")
"""
    # Feed the program over stdin via a heredoc so docker_exec_sh's
    # single bash string stays clean. The 'PY' delimiter is quoted to
    # disable shell expansion inside the heredoc body.
    probe = (
        "/opt/jettstui/.venv/bin/python - <<'PY'\n"
        f"{py_program}"
        "PY"
    )
    end = time.monotonic() + deadline_s
    last_err = ""
    while time.monotonic() < end:
        r = docker_exec_sh(container, probe, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            lines = r.stdout.split("\n", 1)
            try:
                status = int(lines[0].strip())
                body = lines[1] if len(lines) > 1 else ""
                return status, body
            except (ValueError, IndexError) as exc:
                last_err = f"parse: {exc!r} / stdout={r.stdout!r}"
        else:
            last_err = f"rc={r.returncode} stderr={r.stderr!r}"
        time.sleep(0.5)
    raise AssertionError(
        f"Probe of {path} never returned HTTP within {deadline_s}s; "
        f"last error: {last_err}"
    )


def test_dashboard_auth_gate_engages_on_non_loopback_bind(
    built_image: str, container_name: str,
) -> None:
    """A public bind must use the configured dashboard auth provider.

    The s6 run script must not add ``--insecure`` on ``0.0.0.0``. Use the
    bundled local password provider so this image test needs no external
    identity service while still exercising the real auth middleware.

    We verify two independent observable consequences of the gate being
    on:

    1. ``/api/auth/providers`` returns 200 with ``basic`` registered.
    2. ``/api/sessions`` returns 401 without a login cookie.
    3. ``/api/status`` remains public but reports auth_required=True.
    """
    start_container(
        built_image, container_name,
        "FREEIDE_DASHBOARD=1",
        "FREEIDE_DASHBOARD_HOST=0.0.0.0",
        "FREEIDE_DASHBOARD_BASIC_AUTH_USERNAME=admin",
        "FREEIDE_DASHBOARD_BASIC_AUTH_PASSWORD=test-dashboard-pw",
        cmd="sleep 120",
    )

    # (1) Provider registry visible via the public bootstrap endpoint.
    status_code, body = _http_probe(container_name, "/api/auth/providers")
    assert status_code == 200, (
        f"/api/auth/providers should return 200 when a provider is "
        f"registered; got {status_code} body={body!r}"
    )
    payload = json.loads(body)
    provider_names = [p.get("name") for p in payload.get("providers", [])]
    assert "basic" in provider_names, (
        "Bundled password provider should register when its credentials "
        f"are configured. Got: {payload!r}"
    )

    # (2) A gated route (``/api/sessions``) returns 401 to an
    #     unauthenticated caller — the auth gate is intercepting.
    status_code, body = _http_probe(container_name, "/api/sessions")
    assert status_code == 401, (
        "Auth gate must intercept gated /api/* routes on 0.0.0.0 bind "
        "when a provider is registered and FREEIDE_DASHBOARD_INSECURE "
        f"is unset. Got: status={status_code} body={body!r}"
    )

    # (3) ``/api/status`` remains 200 under the gate — it's in the shared
    #     ``PUBLIC_API_PATHS`` allowlist so health checks can reach it
    #     without a cookie.
    status_code, body = _http_probe(container_name, "/api/status")
    assert status_code == 200, (
        "/api/status must remain publicly reachable under the auth gate. "
        f"Got: status={status_code} body={body!r}"
    )
    status = json.loads(body)
    assert status.get("auth_required") is True, (
        "/api/status must report auth_required=True when the auth gate "
        f"is engaged so the client can distinguish modes. Got: {status!r}"
    )


def test_dashboard_insecure_env_var_no_longer_bypasses_gate(
    built_image: str, container_name: str,
) -> None:
    """``FREEIDE_DASHBOARD_INSECURE=1`` NO LONGER disables the auth gate
    (June 2026 hardening). With insecure set on a 0.0.0.0 bind and NO auth
    provider registered, start_server fails closed — the dashboard never
    binds, so ``/api/status`` is unreachable. This proves the unauthenticated
    public-dashboard escape hatch is gone: there is no env that serves the
    dashboard on a public bind without an auth provider.
    """
    start_container(
        built_image, container_name,
        "FREEIDE_DASHBOARD=1",
        "FREEIDE_DASHBOARD_HOST=0.0.0.0",
        "FREEIDE_DASHBOARD_INSECURE=1",
        cmd="sleep 120",
    )
    # Fail-closed: the dashboard process must NOT successfully serve. Probe
    # for a few seconds; /api/status should never become reachable because
    # start_server raised SystemExit before binding.
    ok, _ = poll_container(
        container_name,
        "curl -fsS -m 2 http://127.0.0.1:9119/api/status >/dev/null 2>&1",
        deadline_s=12.0,
    )
    assert not ok, (
        "Dashboard must NOT serve on a public bind with --insecure and no "
        "auth provider — the gate fails closed. /api/status became reachable, "
        "meaning the unauthenticated escape hatch is still open."
    )
