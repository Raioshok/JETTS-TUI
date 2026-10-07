---
sidebar_position: 11
title: Model Catalog
description: Offline fallbacks and silent defaults for provider model discovery.
---

# Model Catalog

JettsTUI discovers models from each provider's live API. For **OpenRouter**, `GET /api/v1/models` is authoritative: a successful response is shown in full and is never restricted or reordered by this manifest.

This manifest supplies offline recovery and the cost-safe silent default. It is consulted for picker rows only when the live provider endpoint is unreachable or unusable; if the manifest is also unavailable, JettsTUI falls back to the in-repo snapshot that ships with the CLI.

## Live manifest URL

```
https://raw.githubusercontent.com/Raioshok/JETTS-TUI/main/resources/model-catalog.json
```

The source of truth is [`resources/model-catalog.json`](../../resources/model-catalog.json) in this repository. The raw GitHub URL serves the version on `main`; no website deployment is involved.

## Schema

```json
{
  "version": 1,
  "updated_at": "2026-04-25T22:00:00Z",
  "metadata": {},
  "providers": {
    "openrouter": {
      "metadata": {},
      "models": [
        {"id": "z-ai/glm-5.2",         "description": "default", "default": true},
        {"id": "moonshotai/kimi-k3",   "description": "recommended", "metadata": {}},
        {"id": "openai/gpt-5.4",       "description": ""}
      ]
    }
  }
}
```

Field notes:

- **`version`** — integer schema version. Future schemas bump this; JettsTUI refuses manifests with versions it doesn't understand and falls back to the hardcoded snapshot.
- **`metadata`** — free-form dict at the manifest, provider, and model level. Any keys. JettsTUI ignores unknown fields, so you can annotate entries (`"tier": "paid"`, `"tags": [...]`, etc.) without coordinating a schema change.
- **`description`** — OpenRouter-only. Drives picker badge text (`"recommended"`, `"free"`, `"default"`, or empty).
- **`default`** — exactly one entry per provider may carry `"default": true`. That model is the **silent default**: what JettsTUI lands on when the user never selected a model (GUI onboarding confirm card, `provider` configured with no `model`, empty `model.default`). Read cache-only at runtime (`get_default_model_from_cache`) so hot resolution paths never hit the network; when no cached manifest exists, JettsTUI falls back to the in-repo `PREFERRED_SILENT_DEFAULT_MODEL` constant, which must match the labeled entry. This lets maintainers rotate the silent default without shipping a release. It is deliberately a capable low-cost model, never the priciest flagship.
- **Pricing and context length** are NOT in the manifest. Those come from live provider APIs (`/v1/models` endpoints, models.dev) at fetch time.

## Fetch behavior

| When | What happens |
|---|---|
| `/model` or `jettstui model` | Uses the provider's live/cached endpoint inventory; this manifest is fallback-only |
| Disk cache fresh (< TTL) | No network hit |
| Network failure with cache | Silent fallback to cache, one log line |
| Network failure, no cache | Silent fallback to in-repo snapshot |
| Manifest fails schema validation | Treated as unreachable |

Cache location: `~/.jettstui/cache/model_catalog.json`.

## Config

```yaml
model_catalog:
  enabled: true
  url: https://raw.githubusercontent.com/Raioshok/JETTS-TUI/main/resources/model-catalog.json
  ttl_hours: 1
  providers: {}
```

Set `enabled: false` to disable remote fetch entirely and always use the in-repo snapshot.

### Per-provider override URLs

Third parties can self-host their own curation list using the same schema. Point a provider at a custom URL:

```yaml
model_catalog:
  providers:
    openrouter:
      url: https://example.com/my-openrouter-curation.json
```

The overriding manifest only needs to populate the provider block(s) it cares about. Other providers continue to resolve against the master URL.

### Hiding providers from the picker

`excluded_providers` lets you hide specific providers from the `/model` picker even when valid credentials exist. Useful when credentials are present for legacy or testing providers that shouldn't appear in normal use (e.g. an old Copilot or OpenRouter token still cached in `auth.json` or discovered via the `gh` CLI).

```yaml
model_catalog:
  excluded_providers:
    - copilot
    - openrouter
    - openai
```

The exclusion is matched case-insensitively against every key a provider can surface under — the JettsTUI id and models.dev id (built-in mapped providers), the overlay pid and resolved JettsTUI slug (overlay providers), and the canonical slug (canonical providers) — so a single entry like `copilot` hides the provider regardless of which section emits it. It is honored by every `/model` picker surface: the gateway interactive/text pickers, the TUI picker, and the interactive `jettstui model` CLI picker. An empty list (or omitting the key) has no effect.

## Updating the manifest

Maintainers:

```bash
# Re-generate from the in-repo hardcoded lists (keeps manifest in sync after
# editing OPENROUTER_MODELS in jettstui/models.py).
python scripts/build_model_catalog.py
```

Then submit the resulting change to `resources/model-catalog.json`. The raw GitHub URL reflects the file after it lands on `main`.

You can also hand-edit the JSON directly for fine-grained metadata changes that don't belong in the in-repo snapshot — the generator script is a convenience, not the single source of truth.
