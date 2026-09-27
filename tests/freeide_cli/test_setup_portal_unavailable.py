"""Do not silently ignore the legacy managed-Portal setup flag."""

from types import SimpleNamespace

import pytest

from freeide_cli.main import cmd_setup


def test_portal_setup_exits_with_actionable_guidance():
    with pytest.raises(SystemExit, match="Managed Portal onboarding is unavailable") as exc:
        cmd_setup(SimpleNamespace(portal=True))

    assert "jetts-tui setup" in str(exc.value)
    assert "--portal flag is retained for compatibility" in str(exc.value)
