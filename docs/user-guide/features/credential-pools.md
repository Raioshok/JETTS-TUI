---
title: Credential Pools
description: Pool multiple API keys or OAuth tokens per provider for automatic rotation and rate limit recovery.
sidebar_label: Credential Pools
sidebar_position: 9
---

# Credential Pools

Credential pools let you register multiple API keys or OAuth tokens for the same provider. When one key hits a rate limit or billing quota, JettsTUI automatically rotates to the next healthy key — keeping your session alive without switching providers.

This is different from [fallback providers](./fallback-providers.md), which switch to a *different* provider entirely. Credential pools are same-provider rotation; fallback providers are cross-provider failover. Pools are tried first — if all pool keys are exhausted, *then* the fallback provider activates.

:::warning Key rotation resets the prompt cache
Provider-side prompt caches (Anthropic, OpenAI, OpenRouter) are scoped to the account/API key that made the request. When the pool rotates to a different key mid-session, the new key has no cached prefix for your conversation — the next request re-reads the full history at undiscounted input price, and rotating back later is another full re-read unless the earlier key's cache TTL is still alive. Rotation keeps your session running, which is the point, but on long conversations each rotation costs one full-price pass over the context.
:::

:::tip
Subscription sign-ins can hold several accounts too: Anthropic, OpenAI Codex, xAI Grok, Qwen, MiniMax, and Google Antigravity. When one account runs out of quota, JettsTUI moves to the next. See [Multiple sign-in accounts](#multiple-sign-in-accounts).
:::

## How It Works

```
Your request
  → Pick key from pool (round_robin / least_used / fill_first / random)
  → Send to provider
  → 429 rate limit?
      → Plan/usage limit reached (e.g. ChatGPT/Codex "usage limit reached")?
          → Rotate to next pool key immediately (no retry — the cap won't clear on retry)
      → Generic / transient 429?
          → Retry same key once (transient blip)
          → Second 429 → rotate to next pool key
      → All keys exhausted → fallback_model (different provider)
  → 402 billing error?
      → Immediately rotate to next pool key (24h cooldown)
  → 401 auth expired?
      → Try refreshing the token (OAuth)
      → Refresh failed → rotate to next pool key
  → Success → continue normally
```

## Quick Start

If you already have an API key set in `.env`, JettsTUI auto-discovers it as a 1-key pool. To benefit from pooling, add more keys:

```bash
# Add a second OpenRouter key
jettstui auth add openrouter --api-key sk-or-v1-your-second-key

# Add a second Anthropic key
jettstui auth add anthropic --type api-key --api-key sk-ant-api03-your-second-key

# Add an Anthropic OAuth credential (requires Claude Max plan + extra usage credits)
jettstui auth add anthropic --type oauth
# Opens browser for OAuth login
```

Check your pools:

```bash
jettstui auth list
```

Output:
```
openrouter (2 credentials):
  #1  OPENROUTER_API_KEY   api_key env:OPENROUTER_API_KEY ←
  #2  backup-key           api_key manual

anthropic (3 credentials):
  #1  jettstui_pkce          oauth   jettstui_pkce ←
  #2  claude_code          oauth   claude_code
  #3  ANTHROPIC_API_KEY    api_key env:ANTHROPIC_API_KEY
```

The `←` marks the currently selected credential.

## Multiple Sign-in Accounts

Subscription providers can hold several sign-in accounts: Anthropic, OpenAI Codex, xAI Grok, Qwen, MiniMax, and Google Antigravity. Add each account by signing in again:

```bash
jettstui auth add openai-codex        # sign in with a second ChatGPT account
jettstui auth add antigravity         # sign in with a second Google account
```

Switch accounts when one runs out of quota:

```bash
jettstui auth use openai-codex        # list the accounts and pick one
jettstui auth use openai-codex 2      # or name it: number, id, or exact label
```

The account you pick stays in use until its quota runs out. JettsTUI then moves to the next account on its own, and goes back to your pick once its quota resets. Picking an account that is on cooldown clears the cooldown, so you can retry it right away.

In the desktop app, open **Settings → Providers**. Each connected provider lists its accounts with **Use**, remove, and **Add account** buttons. The **Usage** tab shows the quota of the account in use and has the same quick switcher. Open chats move to the new account on their next message.

For Google Antigravity, JettsTUI reads Google's `QUOTA_EXHAUSTED` errors and switches accounts in the middle of a request. A short burst limit (a retry hint under a minute) does not switch accounts.

:::note
Switching accounts starts a new provider-side prompt cache, just like key rotation (see the warning above).
:::

## Interactive Management

Run `jettstui auth` with no subcommand for an interactive wizard:

```bash
jettstui auth
```

This shows your full pool status and offers a menu:

```
What would you like to do?
  1. Add a credential
  2. Remove a credential
  3. Reset cooldowns for a provider
  4. Set rotation strategy for a provider
  5. Switch which account a provider uses
  6. Exit
```

For providers that support both API keys and OAuth (Anthropic, JettsTUI, Codex), the add flow asks which type:

```
anthropic supports both API keys and OAuth login.
  1. API key (paste a key from the provider dashboard)
  2. OAuth login (authenticate via browser)
Type [1/2]:
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `jettstui auth` | Interactive pool management wizard |
| `jettstui auth list` | Show all pools and credentials |
| `jettstui auth list <provider>` | Show a specific provider's pool |
| `jettstui auth add <provider>` | Add a credential (prompts for type and key) |
| `jettstui auth add <provider> --type api-key --api-key <key>` | Add an API key non-interactively |
| `jettstui auth add <provider> --type oauth` | Add an OAuth credential via browser login |
| `jettstui auth remove <provider> <index>` | Remove credential by 1-based index |
| `jettstui auth reset <provider>` | Clear all cooldowns/exhaustion status |
| `jettstui auth use <provider> [account]` | Switch the sign-in account a provider uses (lists them when no account is given) |

## Rotation Strategies

Configure via `jettstui auth` → "Set rotation strategy" or in `config.yaml`:

```yaml
credential_pool_strategies:
  openrouter: round_robin
  anthropic: least_used
```

| Strategy | Behavior |
|----------|----------|
| `fill_first` (default) | Use the first healthy key until it's exhausted, then move to the next |
| `round_robin` | Cycle through keys evenly, rotating after each selection |
| `least_used` | Always pick the key with the lowest request count |
| `random` | Random selection among healthy keys |

## Error Recovery

The pool handles different errors differently:

| Error | Behavior | Cooldown |
|-------|----------|----------|
| **429 Rate Limit** | Retry same key once (transient). Second consecutive 429 rotates to next key | 1 hour |
| **402 Billing/Quota** | Immediately rotate to next key | 24 hours |
| **401 Auth Expired** | Try refreshing the OAuth token first. Rotate only if refresh fails | — |
| **All keys exhausted** | Fall through to `fallback_model` if configured | — |

The `has_retried_429` flag resets on every successful API call, so a single transient 429 doesn't trigger rotation.

## Custom Endpoint Pools

Custom OpenAI-compatible endpoints (Together.ai, RunPod, local servers) get their own pools, keyed by the endpoint name from `custom_providers` in config.yaml.

When you set up a custom endpoint via `jettstui model`, it auto-generates a name like "Together.ai" or "Local (localhost:8080)". This name becomes the pool key.

```bash
# After setting up a custom endpoint via jettstui model:
jettstui auth list
# Shows:
#   Together.ai (1 credential):
#     #1  config key    api_key config:Together.ai ←

# Add a second key for the same endpoint:
jettstui auth add Together.ai --api-key sk-together-second-key
```

Custom endpoint pools are stored in `auth.json` under `credential_pool` with a `custom:` prefix:

```json
{
  "credential_pool": {
    "openrouter": [...],
    "custom:together.ai": [...]
  }
}
```

## Auto-Discovery

JettsTUI automatically discovers credentials from multiple sources and seeds the pool on startup:

| Source | Example | Auto-seeded? |
|--------|---------|-------------|
| Environment variables | `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY` | Yes |
| OAuth tokens (auth.json) | Codex device code, JettsTUI device code | Yes |
| Claude Code credentials | `~/.claude/.credentials.json` | Yes (Anthropic) |
| JettsTUI PKCE OAuth | `~/.jettstui/auth.json` | Yes (Anthropic) |
| Custom endpoint config | `model.api_key` in config.yaml | Yes (custom endpoints) |
| Manual entries | Added via `jettstui auth add` | Persisted in auth.json |

Auto-seeded entries are updated on each pool load — if you remove an env var, its pool entry is automatically pruned. Manual entries (added via `jettstui auth add`) are never auto-pruned.

Borrowed runtime secrets (for example env vars, Bitwarden/Vault/keyring/systemd references, and custom config values) are reference-only at the `auth.json` boundary. JettsTUI can use the resolved value in memory for the current run, but it persists only metadata such as the source ref, label, status, request counters, and a non-reversible fingerprint. Manual entries and JettsTUI-owned OAuth/device-code state keep the durable tokens they need to refresh.

## Delegation & Subagent Sharing

When the agent spawns subagents via `delegate_task`, the parent's credential pool is automatically shared with children:

- **Same provider** — the child receives the parent's full pool, enabling key rotation on rate limits
- **Different provider** — the child loads that provider's own pool (if configured)
- **No pool configured** — the child falls back to the inherited single API key

This means subagents benefit from the same rate-limit resilience as the parent, with no extra configuration needed. Per-task credential leasing ensures children don't conflict with each other when rotating keys concurrently.

## Thread Safety

The credential pool uses a threading lock for all state mutations (`select()`, `mark_exhausted_and_rotate()`, `try_refresh_current()`, `mark_used()`). This ensures safe concurrent access when the gateway handles multiple chat sessions simultaneously.

## Architecture

For the full data flow diagram, see [`docs/credential-pool-flow.excalidraw`](https://excalidraw.com/#json=2Ycqhqpi6f12E_3ITyiwh,c7u9jSt5BwrmiVzHGbm87g) in the repository.

The credential pool integrates at the provider resolution layer:

1. **`agent/credential_pool.py`** — Pool manager: storage, selection, rotation, cooldowns
2. **`jettstui/auth_commands.py`** — CLI commands and interactive wizard
3. **`jettstui/runtime_provider.py`** — Pool-aware credential resolution
4. **`run_agent.py`** — Error recovery: 429/402/401 → pool rotation → fallback

## Storage

Pool state is stored in `~/.jettstui/auth.json` under the `credential_pool` key:

```json
{
  "version": 1,
  "credential_pool": {
    "openrouter": [
      {
        "id": "abc123",
        "label": "OPENROUTER_API_KEY",
        "auth_type": "api_key",
        "priority": 0,
        "source": "env:OPENROUTER_API_KEY",
        "secret_source": "bitwarden",
        "secret_fingerprint": "sha256:12ab34cd56ef7890",
        "last_status": "ok",
        "request_count": 142
      }
    ],
    "anthropic": [
      {
        "id": "manual1",
        "label": "personal-api-key",
        "auth_type": "api_key",
        "priority": 0,
        "source": "manual",
        "access_token": "sk-ant-api03-..."
      }
    ]
  }
}
```

The OpenRouter entry above was borrowed from an external source, so the raw key is not stored in `auth.json`. The manual Anthropic entry was intentionally added to JettsTUI' credential store, so its token remains persistable.

Strategies are stored in `config.yaml` (not `auth.json`):

```yaml
credential_pool_strategies:
  openrouter: round_robin
  anthropic: least_used
```
