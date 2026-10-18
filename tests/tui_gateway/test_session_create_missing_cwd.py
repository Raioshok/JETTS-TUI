"""session.create must not silently start a chat outside the folder it was given."""

from tui_gateway import server


def test_missing_folder_is_rejected_instead_of_falling_back_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TERMINAL_ENV", "local")
    moved = tmp_path / "project" / "renamed-away"
    before = set(server._sessions)

    response = server._methods["session.create"]("rid-1", {"source": "desktop", "cwd": str(moved)})

    assert response["error"]["code"] == 4017
    assert str(moved) in response["error"]["message"]
    assert set(server._sessions) == before
