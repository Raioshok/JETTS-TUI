---
sidebar_position: 1
title: "FreeIDE Portal"
description: "One subscription, 300+ frontier models, and the Tool Gateway — the recommended way to run FreeIDE Agent"
---

# FreeIDE Portal

[FreeIDE Portal](https://portal.freeide.dev) is FreeIDE's unified subscription gateway and **the recommended way to run FreeIDE Agent**. One OAuth login replaces the juggling act of separate accounts, API keys, and billing relationships across every model lab, search API, image generator, and browser provider you'd otherwise need to wire up by hand.

If you only have time to set up one thing, set up this. The fastest path:

```bash
freeide setup --portal
```

That single command runs the Portal OAuth, lets you pick a FreeIDE model, sets FreeIDE as your inference provider in `config.yaml`, and turns on the Tool Gateway. You're ready to `freeide chat` immediately after.

Don't have a subscription yet? [portal.freeide.dev/manage-subscription](https://portal.freeide.dev/manage-subscription) — sign up, then come back and run the command above.

## What's in the subscription

### 300+ frontier models, one bill

The Portal proxies a curated catalog of agentic models from across the ecosystem — billed against your FreeIDE subscription instead of one credit balance per lab.

| Family | Models |
|--------|--------|
| **Anthropic Claude** | Opus 4.7, Opus 4.6, Sonnet 4.6, Haiku 4.5 |
| **OpenAI** | GPT-5.5, GPT-5.5 Pro, GPT-5.4 Mini, GPT-5.4 Nano, GPT-5.3 Codex |
| **Google Gemini** | Gemini 3 Pro Preview, Gemini 3 Flash Preview, Gemini 3.1 Pro Preview, Gemini 3.1 Flash Lite Preview |
| **DeepSeek** | DeepSeek V4 Pro |
| **Qwen** | Qwen3.7-Max, Qwen3.6-35B-A3B |
| **Kimi / Moonshot** | Kimi K2.6 |
| **GLM / Zhipu** | GLM-5.1 |
| **MiniMax** | MiniMax M2.7 |
| **xAI** | Grok 4.3 |
| **NVIDIA** | Nemotron-3 Super 120B-A12B |
| **Tencent** | Hunyuan 3 Preview |
| **Xiaomi** | MiMo V2.5 Pro |
| **StepFun** | Step 3.5 Flash |
| **FreeIDE** | FreeIDE-4-70B, FreeIDE-4-405B (chat, see [note below](#a-note-on-freeide-4)) |
| **+ everything else** | 280+ additional models — the full agentic frontier |

Under the hood, the Portal routes each model to the backend best suited for it — some models go through OpenRouter, others through proprietary or secondary providers, and the routing for a given model can change over time. Everything is billed against your FreeIDE subscription either way. Switch between Claude Sonnet 4.6 for code and Gemini 3 Pro for long context with `/model` mid-session — no new credentials, no top-ups, no surprise zero-balance errors.

:::note
Because routing is per-model and not always through OpenRouter, OpenRouter-specific request extensions (such as `provider` routing preferences, `session_id` sticky routing, or top-level `cache_control`) are not part of the Portal's API contract and may be ignored depending on which backend serves the model.
:::

### The FreeIDE Tool Gateway

The same subscription unlocks the [Tool Gateway](/user-guide/features/tool-gateway), which routes FreeIDE Agent's tool calls through FreeIDE-managed infrastructure. Five backends, one login:

| Tool | Partner | What it does |
|------|---------|--------------|
| **Web search & extract** | Firecrawl | Agent-grade search and full-page extraction. No Firecrawl API key, no rate limit babysitting. |
| **Image generation** | FAL | Nine models under one endpoint: FLUX 2 Klein 9B, FLUX 2 Pro, Z-Image Turbo, Nano Banana Pro (Gemini 3 Pro Image), GPT Image 1.5, GPT Image 2, Ideogram V3, Recraft V4 Pro, Qwen Image. |
| **Text-to-speech** | OpenAI TTS | High-quality TTS without a separate OpenAI key. Enables [voice mode](/user-guide/features/voice-mode) across messaging platforms. |
| **Cloud browser automation** | Browser Use | Headless Chromium sessions for `browser_navigate`, `browser_click`, `browser_type`, `browser_vision`. No Browserbase account needed. |
| **Cloud terminal sandbox** | Modal | Serverless terminal sandboxes for code execution (optional add-on). |

Without the gateway, hooking each of those up means a Firecrawl account, a FAL account, a Browser Use account, an OpenAI key, and a Modal account — five separate signups, five separate dashboards, five separate top-up flows. With the gateway, all of it routes through one subscription.

You can also enable just specific gateway tools (e.g. web search but not image generation) — see [Mixing the gateway with your own backends](#mixing-the-gateway-with-your-own-backends) below.

### No credentials in your dotfiles

Because everything routes through one OAuth-authenticated Portal session, you don't accumulate a `.env` file with a dozen long-lived API keys. The refresh token at `~/.freeide/auth.json` is the only credential on disk, and FreeIDE mints short-lived JWTs from it per request — see [Token handling](#token-handling) below.

### Cross-platform parity

[Native Windows](/user-guide/windows-native) makes per-tool API key setup its rough edge — installing a Firecrawl account, a FAL account, a Browser Use account, an OpenAI key from Windows is the highest-friction part of getting a useful agent. A Portal subscription smooths that out: one OAuth covers the model and every gateway tool, so Windows users get the same experience as macOS/Linux without manually configuring four backends.

## A note on FreeIDE 4

FreeIDE's own **FreeIDE 4** family (FreeIDE-4-70B, FreeIDE-4-405B) is available through the Portal at heavily discounted rates. These are **frontier hybrid-reasoning chat models** — strong at math, science, instruction following, schema adherence, roleplay, and long-form writing.

They are **not recommended for use inside FreeIDE Agent**, however. FreeIDE 4 is tuned for chat and reasoning, not the rapid-fire tool-calling loop the agent relies on. Use them for research workflows or via the [subscription proxy](/user-guide/features/subscription-proxy) from other tooling — but for agent work, pick a frontier agentic model from the catalog instead:

```bash
/model anthropic/claude-sonnet-4.6     # best general-purpose agentic model
/model openai/gpt-5.5-pro              # strong reasoning + tool calling
/model google/gemini-3-pro-preview     # huge context window
/model deepseek/deepseek-v4-pro        # cost-effective coder
```

The Portal's own [model info page](https://portal.freeide.dev/info) carries the same warning, so this isn't a FreeIDE-side opinion — it's the official guidance from FreeIDE.

## Setup

### Fresh install — one command

```bash
freeide setup --portal
```

This runs the full setup in one shot:

1. Opens your browser to portal.freeide.dev for OAuth login
2. Stores the refresh token at `~/.freeide/auth.json`
3. Lets you pick a FreeIDE model from the curated list (or skip to keep your current one)
4. Sets FreeIDE as your inference provider in `~/.freeide/config.yaml` (when you pick a model)
5. Turns on the Tool Gateway (web, image, TTS, browser routing)
6. Returns you to your terminal ready to `freeide chat`

If you don't have a subscription yet, sign up at [portal.freeide.dev/manage-subscription](https://portal.freeide.dev/manage-subscription) first.

### Existing install — add Portal alongside other providers

If you already have FreeIDE configured with OpenRouter, Anthropic, or any other provider and you want to add the Portal alongside them:

```bash
freeide model
# pick "FreeIDE Portal" from the provider list
# browser opens, sign in, done
```

Your existing providers stay configured. You can switch between them with `/model` mid-session or `freeide model` between sessions — the Portal becomes one of your available providers, not your only one.

### Headless / SSH / remote setup

OAuth needs a browser, but the loopback callback runs on the machine where FreeIDE is running. For remote hosts, see [OAuth over SSH / Remote Hosts](/guides/oauth-over-ssh) — the same patterns work for the Portal as for any other OAuth-based provider (`ssh -L` port forwarding).

### Profile setup

If you use [FreeIDE profiles](/user-guide/profiles), the Portal refresh token is automatically shared across all profiles via a shared token store. Sign in once on any profile, and the rest pick it up automatically — no need to repeat the OAuth flow per profile.

## Using the Portal day-to-day

### Inspecting what's wired up

```bash
freeide portal            # log in to FreeIDE Portal + set it up (one-shot onboarding)
freeide portal info       # login status, subscription info, model + gateway routing
freeide portal status     # alias for `portal info`
freeide portal tools      # detailed Tool Gateway catalog with per-tool routing
freeide portal open       # open the subscription management page in your browser
```

`freeide portal` (with no subcommand) is the human-readable alias for `freeide auth add nous --type oauth` — it logs you in, lets you pick a FreeIDE model, sets FreeIDE as your inference provider, and offers the Tool Gateway opt-in (identical to `freeide setup --portal`, and the same FreeIDE flow as the first-time quick setup).

`freeide portal info` gives you the high-level overview:

```
  FreeIDE Portal
  ───────────
  Auth:    ✓ logged in
  Portal:  https://portal.freeide.dev
  Model:   ✓ using FreeIDE as inference provider

  Tool Gateway
  ────────────
  Web search & extract  via FreeIDE Portal
  Image generation      via FreeIDE Portal
  Text-to-speech        via FreeIDE Portal
  Browser automation    via FreeIDE Portal
  Cloud terminal        not configured
```

### Switching models

Inside a session:

```bash
/model anthropic/claude-sonnet-4.6
/model openai/gpt-5.5-pro
/model google/gemini-3-pro-preview
```

Or open the picker:

```bash
/model
# arrow keys, enter to select
```

Outside a session (the full setup wizard, useful when adding a new provider):

```bash
freeide model
```

### Mixing the gateway with your own backends

If you already have, say, a Browserbase account and want to keep using it while routing web search and image generation through FreeIDE, that's supported. Use `freeide tools` to pick backends per tool:

```bash
freeide tools
# → Web search       → "FreeIDE Subscription"
# → Image generation → "FreeIDE Subscription"
# → Browser          → "Browserbase"  (your existing key)
# → TTS              → "FreeIDE Subscription"
```

The Tool Gateway is opt-in per tool, not all-or-nothing. The managed backends show up in `freeide tools` whether or not you're logged into FreeIDE Portal — if you pick "FreeIDE Subscription" before authenticating, FreeIDE runs the Portal login inline (it won't change your inference provider or touch your other tools). See the [Tool Gateway docs](/user-guide/features/tool-gateway) for the full per-tool configuration matrix.

### Subscription management

Manage your plan, view usage, or upgrade/cancel at any time:

- **Web:** [portal.freeide.dev/manage-subscription](https://portal.freeide.dev/manage-subscription)
- **CLI shortcut:** `freeide portal open` (opens the same page in your default browser)

## Configuration reference

After `freeide setup --portal`, `~/.freeide/config.yaml` will look like:

```yaml
model:
  provider: nous
  default: anthropic/claude-sonnet-4.6     # or whatever model you picked
  base_url: https://inference-api.freeide.dev/v1
```

The Tool Gateway settings live under their respective tool sections:

```yaml
web:
  backend: nous       # web search/extract routes through Tool Gateway

image_gen:
  provider: nous

tts:
  provider: nous

browser:
  backend: nous
```

The OAuth refresh token is stored separately at `~/.freeide/auth.json` (not in `config.yaml` — credentials and configuration are kept separate by design).

## Token handling

FreeIDE mints a short-lived JWT from your stored Portal refresh token on each inference call rather than reusing a long-lived API key. The token lifecycle is fully automatic — refresh, mint, retry on transient 401 — and you never see it.

If the Portal invalidates the refresh token (password change, manual revoke, session expiry), the invalid refresh token is **quarantined locally** so FreeIDE stops replaying it and you don't see a stream of identical 401s. The next call surfaces a clear "re-authentication required" message. Run `freeide auth add nous` to log in again; the quarantine clears on the next successful login.

## Troubleshooting

### `freeide portal info` shows "not logged in"

You haven't completed the OAuth flow, or your refresh token was wiped. Run:

```bash
freeide portal
```

or use `freeide model` and re-select FreeIDE Portal.

### Got a "re-authentication required" message mid-session

Your Portal refresh token was invalidated (password change, manual revoke, or session expiry). Run `freeide auth add nous` and your next request will use the new credentials. Any quarantine on the old token clears automatically on successful re-login.

### Want to use a specific provider model that the Portal doesn't expose

The Portal routes each model to a suitable backend — some through OpenRouter, others through proprietary or secondary providers — so most models OpenRouter supports are generally available. If a specific model isn't appearing in `/model`, try the OpenRouter-style slug directly:

```bash
/model anthropic/claude-opus-4.6
```

If a model is genuinely missing, [open an issue](https://github.com/freeide/freeide/issues) — we surface the Portal's catalog to FreeIDE and gaps usually mean a routing config we can update.

### Bills not appearing on my Portal account

Check `freeide portal info` first — if it shows you're using a different provider (`Model: currently openrouter` instead of `using FreeIDE as inference provider`), your local config has drifted. Run `freeide model`, pick FreeIDE Portal, and the next request will route through your subscription.

## See also

- **[Tool Gateway](/user-guide/features/tool-gateway)** — Full details on every gateway tool, per-tool config, and pricing
- **[Subscription proxy](/user-guide/features/subscription-proxy)** — Use your Portal subscription from non-FreeIDE tools (other agents, scripts, third-party clients)
- **[Voice mode](/user-guide/features/voice-mode)** — Voice conversations using the Portal's OpenAI TTS
- **[AI Providers](/integrations/providers)** — Full provider catalog if you want to compare alternatives
- **[OAuth over SSH](/guides/oauth-over-ssh)** — Login from remote hosts or browser-only environments
- **[Profiles](/user-guide/profiles)** — Multiple FreeIDE configurations sharing one Portal login
