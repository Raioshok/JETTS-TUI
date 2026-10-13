"""Regression tests for interactive setup provider/model persistence.

Since setup_model_provider delegates to select_provider_and_model()
from jettstui.main, these tests mock the delegation point and verify
that the setup wizard correctly syncs config from disk after the call.
"""

from __future__ import annotations

from jettstui.config import load_config, save_config, save_env_value
from jettstui.setup import _print_setup_summary, setup_model_provider


def _maybe_keep_current_tts(question, choices):
    if question != "Select TTS provider:":
        return None
    assert choices[-1].startswith("Keep current (")
    return len(choices) - 1


def _clear_provider_env(monkeypatch):
    for key in (
        "JETTSTUI_INFERENCE_PROVIDER",
        "OPENAI_BASE_URL",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "GITHUB_TOKEN",
        "GH_TOKEN",
        "GLM_API_KEY",
        "KIMI_API_KEY",
        "MINIMAX_API_KEY",
        "MINIMAX_CN_API_KEY",
        "ANTHROPIC_TOKEN",
        "ANTHROPIC_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


def _stub_tts(monkeypatch):
    monkeypatch.setattr("jettstui.setup.prompt_choice", lambda q, c, d=0: (
        _maybe_keep_current_tts(q, c) if _maybe_keep_current_tts(q, c) is not None
        else d
    ))
    monkeypatch.setattr("jettstui.setup.prompt_yes_no", lambda *a, **kw: False)


def _write_model_config(provider, base_url="", model_name="test-model"):
    """Simulate what a _model_flow_* function writes to disk."""
    cfg = load_config()
    m = cfg.get("model")
    if not isinstance(m, dict):
        m = {"default": m} if m else {}
        cfg["model"] = m
    m["provider"] = provider
    if base_url:
        m["base_url"] = base_url
    else:
        m.pop("base_url", None)
    if model_name:
        m["default"] = model_name
    m.pop("api_mode", None)
    save_config(cfg)


def _write_aux_config(task="compression", provider="gemini", model_name="gemini-2.5-flash"):
    """Simulate the aux picker writing a task override to disk."""
    cfg = load_config()
    aux = cfg.setdefault("auxiliary", {})
    entry = aux.setdefault(task, {})
    entry["provider"] = provider
    entry["model"] = model_name
    save_config(cfg)


def test_setup_model_provider_preserves_auxiliary_choices_written_by_picker(tmp_path, monkeypatch):
    """Aux choices made inside jettstui setup must survive the wizard's final save."""
    monkeypatch.setenv("JETTSTUI_HOME", str(tmp_path))
    _clear_provider_env(monkeypatch)

    config = load_config()
    assert config["auxiliary"]["compression"]["provider"] == "auto"

    def fake_select():
        _write_aux_config("compression", "gemini", "gemini-2.5-flash")

    monkeypatch.setattr("jettstui.main.select_provider_and_model", fake_select)

    setup_model_provider(config, quick=True)
    save_config(config)  # mirrors run_setup_wizard(section="model") final save

    reloaded = load_config()
    compression = reloaded["auxiliary"]["compression"]
    assert compression["provider"] == "gemini"
    assert compression["model"] == "gemini-2.5-flash"


def test_setup_keep_current_custom_from_config_does_not_fall_through(tmp_path, monkeypatch):
    """Keep-current custom should not fall through to the generic model menu."""
    monkeypatch.setenv("JETTSTUI_HOME", str(tmp_path))
    _clear_provider_env(monkeypatch)
    _stub_tts(monkeypatch)

    # Pre-set custom provider
    _write_model_config("custom", "http://localhost:8080/v1", "local-model")

    config = load_config()
    assert config["model"]["provider"] == "custom"

    def fake_select():
        pass  # user chose "cancel" or "keep current"

    monkeypatch.setattr("jettstui.main.select_provider_and_model", fake_select)

    setup_model_provider(config)
    save_config(config)

    reloaded = load_config()
    assert isinstance(reloaded["model"], dict)
    assert reloaded["model"]["provider"] == "custom"
    assert reloaded["model"]["base_url"] == "http://localhost:8080/v1"


def test_setup_keep_current_config_provider_uses_provider_specific_model_menu(
    tmp_path, monkeypatch
):
    """Keeping current provider preserves the config on disk."""
    monkeypatch.setenv("JETTSTUI_HOME", str(tmp_path))
    _clear_provider_env(monkeypatch)
    _stub_tts(monkeypatch)

    _write_model_config("zai", "https://open.bigmodel.cn/api/paas/v4", "glm-5")

    config = load_config()

    def fake_select():
        pass  # keep current

    monkeypatch.setattr("jettstui.main.select_provider_and_model", fake_select)

    setup_model_provider(config)
    save_config(config)

    reloaded = load_config()
    assert isinstance(reloaded["model"], dict)
    assert reloaded["model"]["provider"] == "zai"


def test_setup_copilot_acp_skips_same_provider_pool_step(tmp_path, monkeypatch):
    monkeypatch.setenv("JETTSTUI_HOME", str(tmp_path))
    _clear_provider_env(monkeypatch)

    config = load_config()

    def fake_prompt_choice(question, choices, default=0):
        if question == "Select your inference provider:":
            return 15  # GitHub Copilot ACP
        if question == "Select default model:":
            return 0
        if question == "Configure vision:":
            return len(choices) - 1
        tts_idx = _maybe_keep_current_tts(question, choices)
        if tts_idx is not None:
            return tts_idx
        raise AssertionError(f"Unexpected prompt_choice call: {question}")

    def fake_prompt_yes_no(question, default=True):
        if question == "Add another credential for same-provider fallback?":
            raise AssertionError("same-provider pool prompt should not appear for copilot-acp")
        return False

    monkeypatch.setattr("jettstui.setup.prompt_choice", fake_prompt_choice)
    monkeypatch.setattr("jettstui.setup.prompt_yes_no", fake_prompt_yes_no)
    monkeypatch.setattr("jettstui.setup.prompt", lambda *args, **kwargs: "")
    monkeypatch.setattr("jettstui.auth.get_active_provider", lambda: None)
    monkeypatch.setattr("agent.auxiliary_client.get_available_vision_backends", lambda: [])

    setup_model_provider(config)

    assert config.get("credential_pool_strategies", {}) == {}


def test_setup_copilot_uses_gh_auth_and_saves_provider(tmp_path, monkeypatch):
    """Copilot provider saves correctly through delegation."""
    monkeypatch.setenv("JETTSTUI_HOME", str(tmp_path))
    _clear_provider_env(monkeypatch)
    _stub_tts(monkeypatch)

    config = load_config()

    def fake_select():
        _write_model_config("copilot", "https://models.github.ai/inference/v1", "gpt-4o")

    monkeypatch.setattr("jettstui.main.select_provider_and_model", fake_select)

    setup_model_provider(config)
    save_config(config)

    reloaded = load_config()
    assert isinstance(reloaded["model"], dict)
    assert reloaded["model"]["provider"] == "copilot"


def test_setup_copilot_acp_uses_model_picker_and_saves_provider(tmp_path, monkeypatch):
    """Copilot ACP provider saves correctly through delegation."""
    monkeypatch.setenv("JETTSTUI_HOME", str(tmp_path))
    _clear_provider_env(monkeypatch)
    _stub_tts(monkeypatch)

    config = load_config()

    def fake_select():
        _write_model_config("copilot-acp", "", "claude-sonnet-4")

    monkeypatch.setattr("jettstui.main.select_provider_and_model", fake_select)

    setup_model_provider(config)
    save_config(config)

    reloaded = load_config()
    assert isinstance(reloaded["model"], dict)
    assert reloaded["model"]["provider"] == "copilot-acp"


def test_setup_switch_custom_to_codex_clears_custom_endpoint_and_updates_config(
    tmp_path, monkeypatch
):
    """Switching from custom to codex updates config correctly."""
    monkeypatch.setenv("JETTSTUI_HOME", str(tmp_path))
    _clear_provider_env(monkeypatch)
    _stub_tts(monkeypatch)

    # Start with custom
    _write_model_config("custom", "http://localhost:11434/v1", "qwen3.5:32b")

    config = load_config()
    assert config["model"]["provider"] == "custom"

    def fake_select():
        _write_model_config("openai-codex", "https://api.openai.com/v1", "gpt-4o")

    monkeypatch.setattr("jettstui.main.select_provider_and_model", fake_select)

    setup_model_provider(config)
    save_config(config)

    reloaded = load_config()
    assert isinstance(reloaded["model"], dict)
    assert reloaded["model"]["provider"] == "openai-codex"
    assert reloaded["model"]["default"] == "gpt-4o"


def test_setup_switch_preserves_non_model_config(tmp_path, monkeypatch):
    """Provider switch preserves other config sections (terminal, display, etc.)."""
    monkeypatch.setenv("JETTSTUI_HOME", str(tmp_path))
    _clear_provider_env(monkeypatch)
    _stub_tts(monkeypatch)

    config = load_config()
    config["terminal"]["timeout"] = 999
    save_config(config)

    config = load_config()

    def fake_select():
        _write_model_config("openrouter", model_name="gpt-4o")

    monkeypatch.setattr("jettstui.main.select_provider_and_model", fake_select)

    setup_model_provider(config)
    save_config(config)

    reloaded = load_config()
    assert reloaded["terminal"]["timeout"] == 999
    assert reloaded["model"]["provider"] == "openrouter"


def test_setup_summary_marks_anthropic_auth_as_vision_available(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("JETTSTUI_HOME", str(tmp_path))
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-key")
    monkeypatch.setattr("shutil.which", lambda _name: None)
    monkeypatch.setattr("agent.auxiliary_client.get_available_vision_backends", lambda: ["anthropic"])

    _print_setup_summary(load_config(), tmp_path)
    output = capsys.readouterr().out

    assert "Vision (image analysis)" in output
    assert "missing run 'jettstui setup' to configure" not in output


def test_dahl_provider_in_provider_models_and_profile_api_key():
    """Dahl is recognized in _PROVIDER_MODELS and _is_profile_api_key_provider."""
    import model_tools  # noqa: F401
    from jettstui.models import _PROVIDER_MODELS
    from jettstui.main import _is_profile_api_key_provider
    from providers import get_provider_profile

    assert "dahl" in _PROVIDER_MODELS
    assert len(_PROVIDER_MODELS["dahl"]) >= 3
    assert _is_profile_api_key_provider("dahl") is True
    profile = get_provider_profile("dahl")
    assert profile is not None
    assert profile.auth_type == "api_key"
    assert "MiniMaxAI/MiniMax-M2.7" in profile.fallback_models


def test_get_project_venv_dir_prefers_existing_venv(tmp_path, monkeypatch):
    """_get_project_venv_dir resolves .venv or venv accurately."""
    from jettstui.main import _get_project_venv_dir

    # Empty env
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setattr("jettstui.main.PROJECT_ROOT", tmp_path)

    # 1. Neither exists -> defaults to venv
    assert _get_project_venv_dir() == tmp_path / "venv"

    # 2. .venv exists -> returns .venv
    dot_venv = tmp_path / ".venv"
    dot_venv.mkdir()
    assert _get_project_venv_dir() == dot_venv

    # 3. VIRTUAL_ENV set to a real dir overrides
    custom_venv = tmp_path / "custom_env"
    custom_venv.mkdir()
    monkeypatch.setenv("VIRTUAL_ENV", str(custom_venv))
    assert _get_project_venv_dir() == custom_venv


def test_probe_api_models_caching(monkeypatch):
    """probe_api_models caches responses so repeated probes in setup are fast."""
    from jettstui.models import probe_api_models, _PROBE_API_MODELS_CACHE

    call_count = [0]

    class FakeResp:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass
        def read(self):
            call_count[0] += 1
            return b'{"data": [{"id": "model-1"}, {"id": "model-2"}]}'

    monkeypatch.setattr("jettstui.models._urlopen_model_catalog_request", lambda req, timeout=None: FakeResp())
    _PROBE_API_MODELS_CACHE.clear()

    res1 = probe_api_models("key1", "https://api.testprovider.com/v1")
    assert res1["models"] == ["model-1", "model-2"]
    assert call_count[0] == 1

    # Second call uses cache — no HTTP request made
    res2 = probe_api_models("key1", "https://api.testprovider.com/v1")
    assert res2["models"] == ["model-1", "model-2"]
    assert call_count[0] == 1


def test_prompt_provider_choice_cancel_returns_none(monkeypatch):
    """When user cancels (-1) in curses, _prompt_provider_choice returns None immediately."""
    from jettstui.main import _prompt_provider_choice

    # Return -1 (user pressed ESC in curses)
    monkeypatch.setattr("jettstui.setup._curses_prompt_choice", lambda *a, **k: -1)

    # Should return None directly, without prompting builtins.input
    res = _prompt_provider_choice(["p1", "p2"])
    assert res is None




