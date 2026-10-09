"""The public repository must test its image and never publish upstream's."""

from pathlib import Path

import yaml


WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "docker.yml"
CI_WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


def test_docker_workflow_builds_here_and_publishes_to_own_registry():
    source = WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(source)
    jobs = workflow["jobs"]

    assert workflow["env"]["IMAGE_NAME"] == "ghcr.io/raioshok/jetts-tui"
    assert "if" not in jobs["build"], "PR Docker checks must not silently skip on this repository"
    assert jobs["build"].get("permissions", {"contents": "read"}).get("packages") != "write"

    for name in ("publish", "merge"):
        job = jobs[name]
        assert "Raioshok/JETTS-TUI" in job["if"]
        assert "github.event_name == 'pull_request'" not in job["if"]
        assert job["permissions"]["packages"] == "write"
        login = next(step for step in job["steps"] if "docker/login-action@" in step.get("uses", ""))
        assert login["with"]["registry"] == "ghcr.io"
        assert login["with"]["password"] == "${{ secrets.GITHUB_TOKEN }}"

    assert "DOCKERHUB_" not in source
    assert "jettstui/jettstui" not in source

    ci = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    assert ci["permissions"].get("packages") != "write", "PR-wide CI must not publish packages"
    assert "docker" in ci["jobs"]["all-checks-pass"]["needs"], "A failed PR image build must fail the release gate"
    assert "'cancelled'" in CI_WORKFLOW.read_text(encoding="utf-8"), "Cancelled checks must not pass the release gate"
