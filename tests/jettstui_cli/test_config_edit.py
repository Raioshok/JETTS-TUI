"""Real-file contracts for targeted gateway config edits."""

import yaml

from jettstui import config_edit
from jettstui.config_edit import save_config_value


def test_gateway_config_edit_uses_active_home_and_preserves_siblings(tmp_path, monkeypatch):
    home = tmp_path / "profile-home"
    home.mkdir()
    config_path = home / "config.yaml"
    config_path.write_text(
        "model:\n  default: before\n  provider: openrouter\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("JETTSTUI_HOME", str(home))

    assert save_config_value("model.default", "after")

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert config["model"] == {"default": "after", "provider": "openrouter"}


def test_first_gateway_config_edit_creates_home_config_without_checkout_write(tmp_path, monkeypatch):
    home = tmp_path / "new-home"
    monkeypatch.setenv("JETTSTUI_HOME", str(home))
    monkeypatch.setattr(config_edit, "__file__", str(tmp_path / "jettstui" / "config_edit.py"))
    checkout_config = tmp_path / "cli-config.yaml"
    checkout_config.write_text("model:\n  default: checkout-model\n", encoding="utf-8")

    assert save_config_value("approvals.destructive_slash_confirm", False)

    config = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
    assert config["approvals"]["destructive_slash_confirm"] is False
    assert checkout_config.read_text(encoding="utf-8") == "model:\n  default: checkout-model\n"
