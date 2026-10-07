"""Local tool-capability detection for FreeIDE.

FreeIDE is bring-your-own-key: every optional tool backend (web search, image
and video generation, TTS/STT, browser automation, Modal execution) is
available exactly when the user has configured a working local install or a
direct API key for it. There is no managed gateway and no remote entitlement —
availability is computed purely from local credentials and local runtimes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional, Set

from freeide_cli.config import get_env_value, load_config
from utils import is_truthy_value
from tools.tool_backend_helpers import (
    fal_key_is_configured,
    has_direct_modal_credentials,
    normalize_browser_cloud_provider,
    normalize_modal_mode,
    resolve_modal_backend_state,
    resolve_openai_audio_api_key,
)


_DEFAULT_PLATFORM_TOOLSETS = {
    "cli": "freeide-cli",
}

@dataclass(frozen=True)
class ToolFeatureState:
    key: str
    label: str
    included_by_default: bool
    available: bool
    active: bool
    direct_override: bool
    toolset_enabled: bool
    current_provider: str = ""
    explicit_configured: bool = False


@dataclass(frozen=True)
class ToolFeatures:
    features: Dict[str, ToolFeatureState]
    account_info: Optional[object] = None

    @property
    def web(self) -> ToolFeatureState:
        return self.features["web"]

    @property
    def image_gen(self) -> ToolFeatureState:
        return self.features["image_gen"]

    @property
    def tts(self) -> ToolFeatureState:
        return self.features["tts"]

    @property
    def stt(self) -> ToolFeatureState:
        return self.features["stt"]

    @property
    def browser(self) -> ToolFeatureState:
        return self.features["browser"]

    @property
    def video_gen(self) -> ToolFeatureState:
        return self.features["video_gen"]

    @property
    def modal(self) -> ToolFeatureState:
        return self.features["modal"]

    def items(self) -> Iterable[ToolFeatureState]:
        ordered = ("web", "image_gen", "video_gen", "tts", "stt", "browser", "modal")
        for key in ordered:
            yield self.features[key]


def _model_config_dict(config: Dict[str, object]) -> Dict[str, object]:
    model_cfg = config.get("model")
    if isinstance(model_cfg, dict):
        return dict(model_cfg)
    if isinstance(model_cfg, str) and model_cfg.strip():
        return {"default": model_cfg.strip()}
    return {}


def _toolset_enabled(config: Dict[str, object], toolset_key: str) -> bool:
    from toolsets import resolve_toolset

    platform_toolsets = config.get("platform_toolsets")
    if not isinstance(platform_toolsets, dict) or not platform_toolsets:
        platform_toolsets = {"cli": [_DEFAULT_PLATFORM_TOOLSETS["cli"]]}

    target_tools = set(resolve_toolset(toolset_key))
    if not target_tools:
        return False

    for platform, raw_toolsets in platform_toolsets.items():
        if isinstance(raw_toolsets, list):
            toolset_names = list(raw_toolsets)
        else:
            default_toolset = _DEFAULT_PLATFORM_TOOLSETS.get(platform)
            toolset_names = [default_toolset] if default_toolset else []
        if not toolset_names:
            default_toolset = _DEFAULT_PLATFORM_TOOLSETS.get(platform)
            if default_toolset:
                toolset_names = [default_toolset]

        available_tools: Set[str] = set()
        for toolset_name in toolset_names:
            if not isinstance(toolset_name, str) or not toolset_name:
                continue
            try:
                available_tools.update(resolve_toolset(toolset_name))
            except Exception:
                continue

        if target_tools and target_tools.issubset(available_tools):
            return True

    return False


def _has_agent_browser() -> bool:
    import shutil

    from freeide_constants import agent_browser_runnable

    # Validate the resolved binary actually runs — a dangling global symlink
    # is reported by ``which`` but fails at exec. Fall through to the local
    # node_modules copy, which the validator also checks.
    if agent_browser_runnable(shutil.which("agent-browser")):
        return True
    local_bin = (
        Path(__file__).parent.parent / "node_modules" / ".bin" / "agent-browser"
    )
    return agent_browser_runnable(str(local_bin)) if local_bin.exists() else False


def _local_browser_runnable() -> bool:
    """Return True when the *local* browser backend would actually start.

    The ``agent-browser`` CLI being present is necessary but not sufficient for
    local mode: agent-browser also needs a Chromium build on disk unless the
    Lightpanda engine is selected — text-only navigation needs no Chromium.
    """
    if not _has_agent_browser():
        return False
    try:
        from tools.browser_tool import _chromium_installed, _using_lightpanda_engine
    except Exception:
        return True
    if _using_lightpanda_engine():
        return True
    return _chromium_installed()


def _browser_label(current_provider: str) -> str:
    mapping = {
        "browserbase": "Browserbase",
        "browser-use": "Browser Use",
        "firecrawl": "Firecrawl",
        "camofox": "Camofox",
        "local": "Local browser",
    }
    return mapping.get(current_provider or "local", current_provider or "Local browser")


def _tts_label(current_provider: str) -> str:
    mapping = {
        "openai": "OpenAI TTS",
        "elevenlabs": "ElevenLabs",
        "edge": "Edge TTS",
        "xai": "xAI TTS",
        "mistral": "Mistral Voxtral TTS",
        "neutts": "NeuTTS",
    }
    return mapping.get(current_provider or "edge", current_provider or "Edge TTS")


def _stt_label(current_provider: str) -> str:
    mapping = {
        "openai": "OpenAI Whisper",
        "groq": "Groq Whisper",
        "mistral": "Mistral Voxtral Transcribe",
        "local": "Local faster-whisper",
    }
    return mapping.get(current_provider or "local", current_provider or "Local faster-whisper")


def _local_stt_backend_available() -> bool:
    """Whether a local STT backend could serve transcription right now."""
    if get_env_value("FREEIDE_LOCAL_STT_COMMAND"):
        return True
    try:
        from tools.transcription_tools import _HAS_FASTER_WHISPER

        return bool(_HAS_FASTER_WHISPER)
    except Exception:
        return False


def _resolve_browser_feature_state(
    *,
    browser_tool_enabled: bool,
    browser_provider: str,
    browser_provider_explicit: bool,
    browser_local_available: bool,
    browser_local_runnable: bool,
    direct_camofox: bool,
    direct_browserbase: bool,
    direct_browser_use: bool,
    direct_firecrawl: bool,
) -> tuple[str, bool, bool]:
    """Resolve browser availability using the same precedence as runtime.

    ``browser_local_available`` means "the agent-browser CLI is present" — the
    only local requirement for cloud providers, which host their own Chromium.
    ``browser_local_runnable`` additionally requires a usable local Chromium
    build (or the Lightpanda engine).
    """
    if direct_camofox:
        return "camofox", True, bool(browser_tool_enabled)

    if browser_provider_explicit:
        current_provider = browser_provider or "local"
        if current_provider == "browserbase":
            available = bool(browser_local_available and direct_browserbase)
            active = bool(browser_tool_enabled and available)
            return current_provider, available, active
        if current_provider == "browser-use":
            available = bool(browser_local_available and direct_browser_use)
            active = bool(browser_tool_enabled and available)
            return current_provider, available, active
        if current_provider == "firecrawl":
            available = bool(browser_local_available and direct_firecrawl)
            active = bool(browser_tool_enabled and available)
            return current_provider, available, active
        if current_provider == "camofox":
            return current_provider, False, False

        current_provider = "local"
        available = bool(browser_local_runnable)
        active = bool(browser_tool_enabled and available)
        return current_provider, available, active

    if direct_browser_use:
        available = bool(browser_local_available)
        active = bool(browser_tool_enabled and available)
        return "browser-use", available, active

    if direct_browserbase:
        available = bool(browser_local_available)
        active = bool(browser_tool_enabled and available)
        return "browserbase", available, active

    available = bool(browser_local_runnable)
    active = bool(browser_tool_enabled and available)
    return "local", available, active


def get_tool_features(
    config: Optional[Dict[str, object]] = None,
    *,
    force_fresh: bool = False,
) -> ToolFeatures:
    """Compute per-feature tool availability from local credentials only."""
    if config is None:
        config = load_config() or {}
    config = dict(config)

    web_tool_enabled = _toolset_enabled(config, "web")
    image_tool_enabled = _toolset_enabled(config, "image_gen")
    video_tool_enabled = _toolset_enabled(config, "video_gen")
    tts_tool_enabled = _toolset_enabled(config, "tts")
    browser_tool_enabled = _toolset_enabled(config, "browser")
    modal_tool_enabled = _toolset_enabled(config, "terminal")

    web_cfg = config.get("web") if isinstance(config.get("web"), dict) else {}
    tts_cfg = config.get("tts") if isinstance(config.get("tts"), dict) else {}
    stt_cfg = config.get("stt") if isinstance(config.get("stt"), dict) else {}
    browser_cfg = config.get("browser") if isinstance(config.get("browser"), dict) else {}
    terminal_cfg = config.get("terminal") if isinstance(config.get("terminal"), dict) else {}

    web_backend = str(web_cfg.get("backend") or "").strip().lower()
    web_search_backend = str(web_cfg.get("search_backend") or "").strip().lower()
    web_extract_backend = str(web_cfg.get("extract_backend") or "").strip().lower()
    tts_provider = str(tts_cfg.get("provider") or "edge").strip().lower()
    stt_provider = str(stt_cfg.get("provider") or "local").strip().lower()
    browser_provider_explicit = "cloud_provider" in browser_cfg
    browser_provider = normalize_browser_cloud_provider(
        browser_cfg.get("cloud_provider") if browser_provider_explicit else None
    )
    terminal_backend = str(terminal_cfg.get("backend") or "local").strip().lower()
    modal_mode = normalize_modal_mode(terminal_cfg.get("modal_mode"))

    direct_exa = bool(get_env_value("EXA_API_KEY"))
    direct_firecrawl = bool(get_env_value("FIRECRAWL_API_KEY") or get_env_value("FIRECRAWL_API_URL"))
    direct_parallel = bool(get_env_value("PARALLEL_API_KEY"))
    direct_tavily = bool(get_env_value("TAVILY_API_KEY"))
    direct_searxng = bool(get_env_value("SEARXNG_URL"))
    direct_fal = fal_key_is_configured()
    direct_fal_video = direct_fal
    direct_openai_tts = bool(resolve_openai_audio_api_key())
    direct_elevenlabs = bool(get_env_value("ELEVENLABS_API_KEY"))
    direct_camofox = bool(get_env_value("CAMOFOX_URL"))
    direct_browserbase = bool(get_env_value("BROWSERBASE_API_KEY") and get_env_value("BROWSERBASE_PROJECT_ID"))
    direct_browser_use = bool(get_env_value("BROWSER_USE_API_KEY"))
    direct_modal = has_direct_modal_credentials()

    direct_openai_stt = bool(resolve_openai_audio_api_key())
    direct_groq_stt = bool(get_env_value("GROQ_API_KEY"))
    direct_mistral_stt = bool(get_env_value("MISTRAL_API_KEY"))
    local_stt_available = _local_stt_backend_available()

    modal_state = resolve_modal_backend_state(
        modal_mode,
        has_direct=direct_modal,
        managed_ready=False,
        managed_enabled=False,
    )

    web_active = bool(
        web_tool_enabled
        and (
            (web_backend == "exa" and direct_exa)
            or (web_backend == "firecrawl" and direct_firecrawl)
            or (web_backend == "parallel" and direct_parallel)
            or (web_backend == "tavily" and direct_tavily)
            or (web_backend == "searxng" and direct_searxng)
            or (web_search_backend == "searxng" and direct_searxng)
            or (web_search_backend == "exa" and direct_exa)
            or (web_search_backend == "firecrawl" and direct_firecrawl)
            or (web_search_backend == "parallel" and direct_parallel)
            or (web_search_backend == "tavily" and direct_tavily)
        )
    )
    web_available = bool(direct_exa or direct_firecrawl or direct_parallel or direct_tavily or direct_searxng)

    image_active = bool(image_tool_enabled and direct_fal)
    image_available = bool(direct_fal)

    video_active = bool(video_tool_enabled and direct_fal_video)
    video_available = bool(direct_fal_video)

    tts_current_provider = tts_provider or "edge"
    tts_available = bool(
        tts_current_provider in {"edge", "neutts"}
        or (tts_current_provider == "openai" and direct_openai_tts)
        or (tts_current_provider == "elevenlabs" and direct_elevenlabs)
        or (tts_current_provider == "mistral" and bool(get_env_value("MISTRAL_API_KEY")))
    )
    tts_active = bool(tts_tool_enabled and tts_available)

    stt_current_provider = stt_provider or "local"
    stt_available = bool(
        (stt_current_provider == "local" and local_stt_available)
        or (stt_current_provider == "openai" and direct_openai_stt)
        or (stt_current_provider == "groq" and direct_groq_stt)
        or (stt_current_provider == "mistral" and direct_mistral_stt)
    )
    stt_active = stt_available

    browser_local_available = _has_agent_browser()
    browser_local_runnable = _local_browser_runnable()
    (
        browser_current_provider,
        browser_available,
        browser_active,
    ) = _resolve_browser_feature_state(
        browser_tool_enabled=browser_tool_enabled,
        browser_provider=browser_provider,
        browser_provider_explicit=browser_provider_explicit,
        browser_local_available=browser_local_available,
        browser_local_runnable=browser_local_runnable,
        direct_camofox=direct_camofox,
        direct_browserbase=direct_browserbase,
        direct_browser_use=direct_browser_use,
        direct_firecrawl=direct_firecrawl,
    )

    if terminal_backend != "modal":
        modal_available = True
        modal_active = bool(modal_tool_enabled)
        modal_direct_override = False
    elif modal_state["selected_backend"] == "direct":
        modal_available = True
        modal_active = bool(modal_tool_enabled)
        modal_direct_override = bool(modal_tool_enabled)
    elif modal_mode == "direct":
        modal_available = bool(direct_modal)
        modal_active = False
        modal_direct_override = False
    else:
        modal_available = bool(direct_modal)
        modal_active = False
        modal_direct_override = False

    tts_explicit_configured = False
    raw_tts_cfg = config.get("tts")
    if isinstance(raw_tts_cfg, dict) and "provider" in raw_tts_cfg:
        tts_explicit_configured = tts_provider not in {"", "edge"}

    stt_explicit_configured = False
    raw_stt_cfg = config.get("stt")
    if isinstance(raw_stt_cfg, dict) and "provider" in raw_stt_cfg:
        stt_explicit_configured = stt_provider not in {"", "local"}

    features = {
        "web": ToolFeatureState(
            key="web",
            label="Web tools",
            included_by_default=True,
            available=web_available,
            active=web_active,
            direct_override=web_active,
            toolset_enabled=web_tool_enabled,
            current_provider=web_backend or web_search_backend or "",
            explicit_configured=bool(web_backend or web_search_backend),
        ),
        "image_gen": ToolFeatureState(
            key="image_gen",
            label="Image generation",
            included_by_default=True,
            available=image_available,
            active=image_active,
            direct_override=image_active,
            toolset_enabled=image_tool_enabled,
            current_provider="FAL" if direct_fal else "",
            explicit_configured=direct_fal,
        ),
        "video_gen": ToolFeatureState(
            key="video_gen",
            label="Video generation",
            included_by_default=False,
            available=video_available,
            active=video_active,
            direct_override=video_active,
            toolset_enabled=video_tool_enabled,
            current_provider="FAL" if direct_fal_video else "",
            explicit_configured=direct_fal_video,
        ),
        "tts": ToolFeatureState(
            key="tts",
            label="OpenAI TTS",
            included_by_default=True,
            available=tts_available,
            active=tts_active,
            direct_override=tts_active,
            toolset_enabled=tts_tool_enabled,
            current_provider=_tts_label(tts_current_provider),
            explicit_configured=tts_explicit_configured,
        ),
        "stt": ToolFeatureState(
            key="stt",
            label="Speech-to-text",
            included_by_default=True,
            available=stt_available,
            active=stt_active,
            direct_override=stt_active,
            toolset_enabled=True,
            current_provider=_stt_label(stt_current_provider),
            explicit_configured=stt_explicit_configured,
        ),
        "browser": ToolFeatureState(
            key="browser",
            label="Browser automation",
            included_by_default=True,
            available=browser_available,
            active=browser_active,
            direct_override=browser_active,
            toolset_enabled=browser_tool_enabled,
            current_provider=_browser_label(browser_current_provider),
            explicit_configured=browser_provider_explicit,
        ),
        "modal": ToolFeatureState(
            key="modal",
            label="Modal execution",
            included_by_default=False,
            available=modal_available,
            active=modal_active,
            direct_override=terminal_backend == "modal" and modal_direct_override,
            toolset_enabled=modal_tool_enabled,
            current_provider="Modal" if terminal_backend == "modal" else terminal_backend or "local",
            explicit_configured=terminal_backend == "modal",
        ),
    }

    return ToolFeatures(features=features, account_info=None)


def apply_managed_defaults(
    config: Dict[str, object],
    *,
    enabled_toolsets: Optional[Iterable[str]] = None,
    force_fresh: bool = False,
) -> set:
    """No managed gateway in FreeIDE — nothing to auto-configure."""
    return set()


def ensure_tool_backend_access(*args, **kwargs) -> bool:
    """No remote entitlement gate in FreeIDE — local backends are always allowed."""
    return True


def prompt_enable_tool_gateway(config: Optional[Dict[str, object]] = None) -> None:
    """No managed tool gateway in FreeIDE — nothing to prompt."""
    return None
