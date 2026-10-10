"""Default STT language contract.

The global ``stt.language`` defaults to "" (auto-detect) so speech in any
language is transcribed as spoken; pinning English turned non-English speech
into English-sounding nonsense. Users who want a fixed language set its code.
"""

from jettstui.config import DEFAULT_CONFIG
from tools.transcription_tools import _resolve_stt_language

PROVIDERS = ("local", "groq", "openai", "mistral", "xai", "elevenlabs", "deepinfra")


class TestDefaultSttLanguage:
    def test_default_config_auto_detects_for_every_provider(self, monkeypatch):
        monkeypatch.delenv("JETTSTUI_LOCAL_STT_LANGUAGE", raising=False)
        stt = DEFAULT_CONFIG["stt"]
        for provider in PROVIDERS:
            assert _resolve_stt_language(provider, stt) is None, provider

    def test_global_language_pins_every_provider(self, monkeypatch):
        monkeypatch.delenv("JETTSTUI_LOCAL_STT_LANGUAGE", raising=False)
        stt = dict(DEFAULT_CONFIG["stt"])
        stt["language"] = "pt"
        for provider in PROVIDERS:
            assert _resolve_stt_language(provider, stt) == "pt", provider

    def test_per_provider_still_wins_over_global(self, monkeypatch):
        monkeypatch.delenv("JETTSTUI_LOCAL_STT_LANGUAGE", raising=False)
        stt = dict(DEFAULT_CONFIG["stt"])
        stt["language"] = "en"
        stt["groq"] = {"language": "he"}
        assert _resolve_stt_language("groq", stt) == "he"
