"""The SSH backend reuses ONE ControlMaster connection for every command.

These cover the flag builder that decides how long that single connection is
kept and how it's kept alive — the knobs that stop a long session dropping to a
per-command reconnect (which is what used to fail intermittently).
"""

from tools.environments.ssh import ssh_connection_opts


def _opt(opts, key):
    """Value of the first ``-o Key=Value`` flag for ``key`` (or None)."""
    for i in range(0, len(opts) - 1, 2):
        if opts[i] == "-o" and opts[i + 1].startswith(f"{key}="):
            return opts[i + 1].split("=", 1)[1]
    return None


def test_connection_is_always_multiplexed_over_one_socket():
    opts = ssh_connection_opts("/tmp/s.sock")
    assert _opt(opts, "ControlPath") == "/tmp/s.sock"
    assert _opt(opts, "ControlMaster") == "auto"


def test_session_default_keeps_the_connection_for_the_whole_session():
    opts = ssh_connection_opts("/tmp/s.sock")
    # "session" -> ControlPersist=yes (held until cleanup closes it), not the
    # old fixed 300s that dropped after 5 min idle.
    assert _opt(opts, "ControlPersist") == "yes"
    # ...kept alive so an idle master isn't silently dropped.
    assert _opt(opts, "ServerAliveInterval") == "15"
    assert _opt(opts, "ServerAliveCountMax") == "4"


def test_numeric_persist_caps_the_idle_lifetime():
    assert _opt(ssh_connection_opts("/s", control_persist=600), "ControlPersist") == "600"
    assert _opt(ssh_connection_opts("/s", control_persist="600"), "ControlPersist") == "600"


def test_non_numeric_or_zero_persist_is_session_long():
    for value in ("session", "yes", "forever", "", 0, -5):
        assert _opt(ssh_connection_opts("/s", control_persist=value), "ControlPersist") == "yes"


def test_keepalives_can_be_disabled():
    opts = ssh_connection_opts("/s", keepalive_interval=0)
    assert _opt(opts, "ServerAliveInterval") is None
    assert _opt(opts, "ServerAliveCountMax") is None


def test_keepalive_count_is_floored_to_one():
    assert _opt(ssh_connection_opts("/s", keepalive_interval=20, keepalive_count=0), "ServerAliveCountMax") == "1"
