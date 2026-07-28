# Langfuse Observability Plugin

This plugin ships bundled with FreeIDE but is **opt-in** — it only loads when
you explicitly enable it.

## Enable

Pick one:

```bash
# Interactive: walks you through credentials + SDK install + enable
freeide tools  # → Langfuse Observability

# Manual
pip install langfuse
freeide plugins enable observability/langfuse
```

## Required credentials

Set these in `~/.freeide/.env` (or via `freeide tools`):

```bash
FREEIDE_LANGFUSE_PUBLIC_KEY=pk-lf-...
FREEIDE_LANGFUSE_SECRET_KEY=sk-lf-...
FREEIDE_LANGFUSE_BASE_URL=https://cloud.langfuse.com   # or your self-hosted URL
```

Without the SDK or credentials the hooks no-op silently — the plugin fails
open.

## Verify

```bash
freeide plugins list                 # observability/langfuse should show "enabled"
freeide chat -q "hello"              # then check Langfuse for a "FreeIDE turn" trace
```

## Optional tuning

```bash
FREEIDE_LANGFUSE_ENV=production       # environment tag
FREEIDE_LANGFUSE_RELEASE=v1.0.0       # release tag
FREEIDE_LANGFUSE_SAMPLE_RATE=0.5      # sample 50% of traces
FREEIDE_LANGFUSE_MAX_CHARS=12000      # max chars per field (default: 12000)
FREEIDE_LANGFUSE_DEBUG=true           # verbose plugin logging
```

## Disable

```bash
freeide plugins disable observability/langfuse
```
