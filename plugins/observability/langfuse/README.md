# Langfuse Observability Plugin

This plugin ships bundled with JettsTUI but is **opt-in** — it only loads when
you explicitly enable it.

## Enable

Pick one:

```bash
# Interactive: walks you through credentials + SDK install + enable
jettstui tools  # → Langfuse Observability

# Manual
pip install langfuse
jettstui plugins enable observability/langfuse
```

## Required credentials

Set these in `~/.jettstui/.env` (or via `jettstui tools`):

```bash
JETTSTUI_LANGFUSE_PUBLIC_KEY=pk-lf-...
JETTSTUI_LANGFUSE_SECRET_KEY=sk-lf-...
JETTSTUI_LANGFUSE_BASE_URL=https://cloud.langfuse.com   # or your self-hosted URL
```

Without the SDK or credentials the hooks no-op silently — the plugin fails
open.

## Verify

```bash
jettstui plugins list                 # observability/langfuse should show "enabled"
jettstui chat -q "hello"              # then check Langfuse for a "JettsTUI turn" trace
```

## Optional tuning

```bash
JETTSTUI_LANGFUSE_ENV=production       # environment tag
JETTSTUI_LANGFUSE_RELEASE=v1.0.0       # release tag
JETTSTUI_LANGFUSE_SAMPLE_RATE=0.5      # sample 50% of traces
JETTSTUI_LANGFUSE_MAX_CHARS=12000      # max chars per field (default: 12000)
JETTSTUI_LANGFUSE_DEBUG=true           # verbose plugin logging
```

## Disable

```bash
jettstui plugins disable observability/langfuse
```
