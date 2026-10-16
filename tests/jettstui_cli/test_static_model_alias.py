"""Static alias resolution (`sonnet`, `opus`, …) against provider catalogs.

The catalogs are patched so these assert resolution *rules*, not today's
model lists.
"""

from unittest.mock import patch

from jettstui import models


def _resolve(alias, catalog, current):
    with patch.dict(models._PROVIDER_MODELS, catalog, clear=True):
        return models._resolve_static_model_alias(alias, set(current))


def test_alias_newer_than_catalog_relaxes_only_the_version():
    catalog = {"anthropic": ["claude-haiku-4-5", "claude-sonnet-5"]}
    assert _resolve("sonnet", catalog, {"anthropic"}) == ("anthropic", "claude-sonnet-5")


def test_alias_never_falls_through_to_another_model_line():
    # No opus in the catalog: resolving to a sonnet/haiku entry would silently
    # switch the user to a different model.
    catalog = {"anthropic": ["claude-sonnet-5", "claude-haiku-4-5"]}
    assert _resolve("opus", catalog, {"anthropic"}) is None


def test_exact_family_match_beats_version_relaxed_match_on_current_provider():
    catalog = {"bedrock": ["claude-sonnet-5"], "anthropic": ["claude-sonnet-5-5"]}
    assert _resolve("sonnet", catalog, {"bedrock", "anthropic"}) == ("anthropic", "claude-sonnet-5-5")


def test_versioned_claude_shorthand_stays_on_the_current_provider():
    from jettstui import model_switch

    catalogs = {
        "anthropic": ["claude-opus-5-5", "claude-sonnet-5-5"],
        "antigravity": ["claude-opus-5-5-thinking", "claude-sonnet-5-5"],
    }
    for provider, catalog in catalogs.items():
        with patch.object(model_switch, "list_provider_models", lambda _p, c=catalog: list(c)):
            resolved = model_switch.resolve_alias("opus 5.5", provider)
        assert resolved is not None and resolved[0] == provider
        assert resolved[1].startswith("claude-opus-5-5")


def test_no_builtin_direct_alias_pins_claude_to_a_non_anthropic_provider():
    from jettstui import model_switch

    # Direct aliases win over everything (including the reverse lookup by full
    # model id), so pinning a Claude model elsewhere would hijack every
    # Anthropic user who types it.
    for alias in model_switch._BUILTIN_DIRECT_ALIASES.values():
        if alias.model.lower().startswith("claude-"):
            assert alias.provider == "anthropic"


def test_normalize_provider_is_idempotent():
    from jettstui.providers import ALIASES, JETTSTUI_OVERLAYS, normalize_provider

    for name in set(ALIASES) | set(ALIASES.values()) | set(JETTSTUI_OVERLAYS):
        once = normalize_provider(name)
        assert normalize_provider(once) == once, name
