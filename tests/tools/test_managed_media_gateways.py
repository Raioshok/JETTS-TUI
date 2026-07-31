import sys
import types
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest


TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"


def _load_tool_module(module_name: str, filename: str):
    spec = spec_from_file_location(module_name, TOOLS_DIR / filename)
    assert spec and spec.loader
    module = module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _restore_tool_and_agent_modules():
    original_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "tools"
        or name.startswith("tools.")
        or name == "agent"
        or name.startswith("agent.")
        or name in {"fal_client", "openai"}
    }
    try:
        yield
    finally:
        for name in list(sys.modules):
            if (
                name == "tools"
                or name.startswith("tools.")
                or name == "agent"
                or name.startswith("agent.")
                or name in {"fal_client", "openai"}
            ):
                sys.modules.pop(name, None)
        sys.modules.update(original_modules)


def _install_fake_tools_package():
    tools_package = types.ModuleType("tools")
    tools_package.__path__ = [str(TOOLS_DIR)]  # type: ignore[attr-defined]
    sys.modules["tools"] = tools_package
    sys.modules["tools.debug_helpers"] = types.SimpleNamespace(
        DebugSession=lambda *args, **kwargs: types.SimpleNamespace(
            active=False,
            session_id="debug-session",
            log_call=lambda *a, **k: None,
            save=lambda: None,
            get_session_info=lambda: {},
        )
    )
    sys.modules["tools.managed_tool_gateway"] = _load_tool_module(
        "tools.managed_tool_gateway",
        "managed_tool_gateway.py",
    )


def _install_fake_fal_client(captured):
    def submit(model, arguments=None, headers=None):
        raise AssertionError("managed FAL gateway mode should use fal_client.SyncClient")

    class FakeResponse:
        def json(self):
            return {
                "request_id": "req-123",
                "response_url": "http://127.0.0.1:3009/requests/req-123",
                "status_url": "http://127.0.0.1:3009/requests/req-123/status",
                "cancel_url": "http://127.0.0.1:3009/requests/req-123/cancel",
            }

    def _maybe_retry_request(client, method, url, json=None, timeout=None, headers=None):
        captured["submit_via"] = "managed_client"
        captured["http_client"] = client
        captured["method"] = method
        captured["submit_url"] = url
        captured["arguments"] = json
        captured["timeout"] = timeout
        captured["headers"] = headers
        return FakeResponse()

    class SyncRequestHandle:
        def __init__(self, request_id, response_url, status_url, cancel_url, client):
            captured["request_id"] = request_id
            captured["response_url"] = response_url
            captured["status_url"] = status_url
            captured["cancel_url"] = cancel_url
            captured["handle_client"] = client

    class SyncClient:
        def __init__(self, key=None, default_timeout=120.0):
            captured["sync_client_inits"] = captured.get("sync_client_inits", 0) + 1
            captured["client_key"] = key
            captured["client_timeout"] = default_timeout
            self.default_timeout = default_timeout
            self._client = object()

    fal_client_module = types.SimpleNamespace(
        submit=submit,
        SyncClient=SyncClient,
        client=types.SimpleNamespace(
            _maybe_retry_request=_maybe_retry_request,
            _raise_for_status=lambda response: None,
            SyncRequestHandle=SyncRequestHandle,
        ),
    )
    sys.modules["fal_client"] = fal_client_module
    return fal_client_module


def _install_fake_openai_module(captured, transcription_response=None):
    class FakeSpeechResponse:
        def stream_to_file(self, output_path):
            captured["stream_to_file"] = output_path

    class FakeOpenAI:
        def __init__(self, api_key, base_url, **kwargs):
            captured["api_key"] = api_key
            captured["base_url"] = base_url
            captured["client_kwargs"] = kwargs
            captured["close_calls"] = captured.get("close_calls", 0)

            def create_speech(**kwargs):
                captured["speech_kwargs"] = kwargs
                return FakeSpeechResponse()

            def create_transcription(**kwargs):
                captured["transcription_kwargs"] = kwargs
                return transcription_response

            self.audio = types.SimpleNamespace(
                speech=types.SimpleNamespace(
                    create=create_speech
                ),
                transcriptions=types.SimpleNamespace(
                    create=create_transcription
                ),
            )

        def close(self):
            captured["close_calls"] += 1

    fake_module = types.SimpleNamespace(
        OpenAI=FakeOpenAI,
        APIError=Exception,
        APIConnectionError=Exception,
        APITimeoutError=Exception,
    )
    sys.modules["openai"] = fake_module


def test_openai_tts_keeps_direct_only_model_with_direct_key(monkeypatch, tmp_path):
    """With a direct key, the user's tts-1-hd is honored (not coerced)."""
    captured = {}
    _install_fake_tools_package()
    _install_fake_openai_module(captured)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-direct-key")
    monkeypatch.delenv("VOICE_TOOLS_OPENAI_KEY", raising=False)

    tts_tool = _load_tool_module("tools.tts_tool", "tts_tool.py")
    output_path = tmp_path / "speech.mp3"
    tts_tool._generate_openai_tts(
        "hello world", str(output_path), {"openai": {"model": "tts-1-hd"}}
    )

    assert captured["base_url"] == "https://api.openai.com/v1"
    assert captured["speech_kwargs"]["model"] == "tts-1-hd"


def test_openai_tts_accepts_openai_api_key_as_direct_fallback(monkeypatch, tmp_path):
    captured = {}
    _install_fake_tools_package()
    _install_fake_openai_module(captured)
    monkeypatch.delenv("VOICE_TOOLS_OPENAI_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-direct-key")

    tts_tool = _load_tool_module("tools.tts_tool", "tts_tool.py")
    output_path = tmp_path / "speech.mp3"
    tts_tool._generate_openai_tts("hello world", str(output_path), {"openai": {}})

    assert captured["api_key"] == "openai-direct-key"
    assert captured["base_url"] == "https://api.openai.com/v1"
    assert captured["close_calls"] == 1


PLUGINS_DIR = Path(__file__).resolve().parents[2] / "plugins"


def _load_video_gen_plugin(monkeypatch):
    """Load the FAL video gen plugin in isolation."""
    _install_fake_tools_package()

    # Also need the agent.video_gen_provider ABC
    agent_dir = Path(__file__).resolve().parents[2] / "agent"
    spec = spec_from_file_location(
        "agent.video_gen_provider",
        agent_dir / "video_gen_provider.py",
    )
    assert spec and spec.loader
    mod = module_from_spec(spec)
    sys.modules["agent.video_gen_provider"] = mod
    spec.loader.exec_module(mod)

    # Load the plugin
    plugin_init = PLUGINS_DIR / "video_gen" / "fal" / "__init__.py"
    spec = spec_from_file_location("plugins.video_gen.fal", plugin_init)
    assert spec and spec.loader
    plugin_mod = module_from_spec(spec)
    sys.modules["plugins.video_gen.fal"] = plugin_mod
    spec.loader.exec_module(plugin_mod)
    return plugin_mod


def test_video_gen_direct_mode_when_fal_key_set(monkeypatch):
    """When FAL_KEY is set and gateway not preferred, uses direct fal_client.submit."""
    captured = {}
    _install_fake_fal_client(captured)
    monkeypatch.setenv("FAL_KEY", "direct-fal-key-123")
    monkeypatch.delenv("FAL_QUEUE_GATEWAY_URL", raising=False)
    monkeypatch.delenv("TOOL_GATEWAY_USER_TOKEN", raising=False)

    plugin = _load_video_gen_plugin(monkeypatch)
    monkeypatch.setattr(plugin.uuid, "uuid4", lambda: "direct-456")

    # Trigger the lazy load so _fal_client is populated from our fake
    plugin._load_fal_client()

    # In direct mode, fal_client.submit is the module-level function.
    # Our fake raises AssertionError from the managed path, so we need
    # to patch it to actually capture the call.
    direct_captured = {}

    def direct_submit(endpoint, arguments=None, headers=None):
        direct_captured["endpoint"] = endpoint
        direct_captured["arguments"] = arguments
        direct_captured["headers"] = headers
        # Return a mock handle
        class FakeHandle:
            def get(self):
                return {"video": {"url": "https://fal.media/result.mp4"}}
        return FakeHandle()

    plugin._fal_client.submit = direct_submit

    plugin._submit_fal_video_request(
        "fal-ai/pixverse/v6/text-to-video",
        {"prompt": "test direct"},
    )

    assert direct_captured["endpoint"] == "fal-ai/pixverse/v6/text-to-video"
    assert direct_captured["arguments"] == {"prompt": "test direct"}
    assert direct_captured["headers"] == {"x-idempotency-key": "direct-456"}
    # Managed client should NOT have been initialized
    assert "submit_via" not in captured


def test_video_gen_happy_horse_uses_alibaba_namespace():
    """Verify the happy-horse family uses alibaba/ not fal-ai/ endpoints."""
    _install_fake_tools_package()

    # Load just the plugin module to check the catalog
    plugin_init = PLUGINS_DIR / "video_gen" / "fal" / "__init__.py"

    agent_dir = Path(__file__).resolve().parents[2] / "agent"
    spec = spec_from_file_location(
        "agent.video_gen_provider",
        agent_dir / "video_gen_provider.py",
    )
    mod = module_from_spec(spec)
    sys.modules["agent.video_gen_provider"] = mod
    spec.loader.exec_module(mod)

    spec = spec_from_file_location("plugins.video_gen.fal", plugin_init)
    plugin_mod = module_from_spec(spec)
    sys.modules["plugins.video_gen.fal"] = plugin_mod
    spec.loader.exec_module(plugin_mod)

    hh = plugin_mod.FAL_FAMILIES["happy-horse"]
    assert hh["text_endpoint"] == "alibaba/happy-horse/text-to-video"
    assert hh["image_endpoint"] == "alibaba/happy-horse/image-to-video"
