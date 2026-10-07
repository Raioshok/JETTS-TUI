"""Real filesystem tests for default-home migration and compatibility aliases."""

from pathlib import Path
import sys
import pytest

from jettstui_home import default_home_paths, migrate_default_home


def test_default_paths_are_platform_specific(tmp_path: Path) -> None:
    assert default_home_paths(platform="linux", home=tmp_path) == (
        tmp_path / ".jettstui", tmp_path / ".freeide",
    )
    local = tmp_path / "AppData" / "Local"
    assert default_home_paths(platform="win32", home=tmp_path, local_appdata=str(local)) == (
        local / "jettstui", local / "freeide",
    )


def test_migration_moves_data_and_preserves_legacy_access(tmp_path: Path) -> None:
    root = tmp_path / "home with spaces"
    root.mkdir()
    new, old = default_home_paths(platform=sys.platform, home=root, local_appdata=str(root))
    old.mkdir()
    (old / "state.db").write_bytes(b"sessions")

    assert migrate_default_home(new, old, platform=sys.platform) == new
    assert (new / "state.db").read_bytes() == b"sessions"
    assert old.is_dir()
    assert (old / "state.db").read_bytes() == b"sessions"


def test_collision_does_not_merge_or_overwrite(tmp_path: Path) -> None:
    new, old = default_home_paths(platform="linux", home=tmp_path)
    old.mkdir()
    new.mkdir()
    (old / "config.yaml").write_text("old", encoding="utf-8")
    (new / "config.yaml").write_text("new", encoding="utf-8")

    assert migrate_default_home(new, old, platform="linux") == new
    assert (old / "config.yaml").read_text(encoding="utf-8") == "old"
    assert (new / "config.yaml").read_text(encoding="utf-8") == "new"


def test_alias_failure_rolls_back_without_losing_data(tmp_path: Path, monkeypatch) -> None:
    import jettstui_home

    new, old = default_home_paths(platform="linux", home=tmp_path)
    old.mkdir()
    (old / "config.yaml").write_text("keep", encoding="utf-8")
    monkeypatch.setattr(jettstui_home, "_create_compat_alias", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("denied")))

    assert migrate_default_home(new, old, platform="linux") == old
    assert (old / "config.yaml").read_text(encoding="utf-8") == "keep"
    assert not new.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows legacy-home precedence")
def test_runtime_moves_active_windows_home_but_preserves_older_home(tmp_path: Path, monkeypatch) -> None:
    import jettstui_constants

    local = tmp_path / "Local"
    local.mkdir()
    active = local / "freeide"
    active.mkdir()
    (active / "state.db").write_bytes(b"active")
    older = tmp_path / ".freeide"
    older.mkdir()
    (older / "notes.txt").write_text("preserve", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.delenv("JETTSTUI_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert jettstui_constants.get_jettstui_home() == local / "jettstui"
    assert (local / "jettstui" / "state.db").read_bytes() == b"active"
    assert (active / "state.db").read_bytes() == b"active"
    assert (older / "notes.txt").read_text(encoding="utf-8") == "preserve"


def test_explicit_home_does_not_move_default(tmp_path: Path, monkeypatch) -> None:
    import jettstui_constants

    old = tmp_path / ".freeide"
    old.mkdir()
    custom = tmp_path / "custom"
    monkeypatch.setenv("JETTSTUI_HOME", str(custom))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert jettstui_constants.get_jettstui_home() == custom
    assert old.is_dir()
    assert not (tmp_path / ".jettstui").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows installer persisted the old default")
def test_legacy_installer_env_default_migrates(tmp_path: Path, monkeypatch) -> None:
    import jettstui_constants

    old = tmp_path / "freeide"
    old.mkdir()
    (old / "config.yaml").write_text("active", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("JETTSTUI_HOME", str(old))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert jettstui_constants.get_jettstui_home() == tmp_path / "jettstui"
    assert (old / "config.yaml").read_text(encoding="utf-8") == "active"
