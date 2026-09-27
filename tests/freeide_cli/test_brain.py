from __future__ import annotations

import json
from pathlib import Path

import yaml

from freeide_cli.brain import (
    FOLDERS,
    brain_doctor,
    brain_status,
    build_maintenance_prompt,
    capture,
    handle_brain_slash,
    setup_brain,
)
from freeide_cli.commands import resolve_command


def _setup(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    vault = tmp_path / "vault"
    project = tmp_path / "example-project"
    project.mkdir()
    monkeypatch.setenv("FREEIDE_HOME", str(home))
    return setup_brain(vault, project_path=project), home, vault, project


def test_setup_creates_complete_vault_and_persists_config(tmp_path, monkeypatch):
    result, home, vault, project = _setup(tmp_path, monkeypatch)

    assert result.vault == vault.resolve()
    assert all((vault / folder).is_dir() for folder in FOLDERS)
    assert (vault / "Dashboard.md").exists()
    assert (vault / ".obsidian" / "app.json").exists()
    assert (vault / "00-System" / "Brain.base").exists()
    assert (vault / "01-Projects" / project.name / "project-index.md").exists()
    assert (vault / "07-ContextCache" / "Project" / f"{project.name}-source-manifest.json").exists()
    assert (vault / ".freeide-brain.json").exists()

    config = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
    assert config["obsidian"]["vault_path"] == str(vault.resolve())
    assert config["obsidian"]["brain"]["enabled"] is True


def test_setup_is_idempotent_and_preserves_human_edits(tmp_path, monkeypatch):
    _, _, vault, project = _setup(tmp_path, monkeypatch)
    dashboard = vault / "Dashboard.md"
    dashboard.write_text("# My custom dashboard\n", encoding="utf-8")

    result = setup_brain(vault, project_path=project)

    assert dashboard.read_text(encoding="utf-8") == "# My custom dashboard\n"
    assert "Dashboard.md" in result.preserved
    assert not result.created


def test_capture_status_and_doctor_form_a_working_loop(tmp_path, monkeypatch):
    _, _, vault, _ = _setup(tmp_path, monkeypatch)
    inbox = capture("Decide whether to add embeddings", vault)

    assert "Decide whether" in inbox.read_text(encoding="utf-8")
    assert brain_status(vault)["inbox_items"] == 1
    assert brain_doctor(vault)["ok"] is True

    (vault / "02-Knowledge" / "broken.md").write_text("[[Missing Note]]", encoding="utf-8")
    report = brain_doctor(vault)
    assert report["ok"] is False
    assert report["unresolved_links"] == ["Missing Note"]


def test_maintenance_prompt_is_incremental_and_change_gated(tmp_path, monkeypatch):
    _, _, vault, project = _setup(tmp_path, monkeypatch)

    sync = build_maintenance_prompt("sync", vault, project_path=project)
    improve = build_maintenance_prompt("improve", vault, project_path=project)

    assert str(vault.resolve()) in sync
    assert str(project.resolve()) in sync
    assert "SHA-256" in sync
    assert "inspect only added, changed, moved, or" in sync
    assert "If there is no material change" in improve
    assert "make no edits" in improve


def test_slash_command_queues_a_normal_agent_turn(tmp_path, monkeypatch):
    _, _, vault, project = _setup(tmp_path, monkeypatch)
    result = handle_brain_slash("/brain improve", cwd=project)

    assert result.prompt is not None
    assert "conflict-aware improvement" in result.prompt
    assert str(vault.resolve()) in result.prompt
    assert resolve_command("brain").name == "brain"


def test_manifest_tracks_only_generator_owned_content(tmp_path, monkeypatch):
    _, _, vault, _ = _setup(tmp_path, monkeypatch)
    manifest = json.loads((vault / ".freeide-brain.json").read_text(encoding="utf-8"))

    assert manifest["schema_version"] == 1
    assert "Dashboard.md" in manifest["managed"]
    assert "11-Inbox/Inbox.md" in manifest["managed"]
