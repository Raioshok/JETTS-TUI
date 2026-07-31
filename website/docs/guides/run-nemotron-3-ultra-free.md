---
sidebar_position: 0
title: "Run Nemotron 3 Ultra free in FreeIDE Agent"
description: "Try NVIDIA Nemotron 3 Ultra free — June 4–18 — with day 0 support in FreeIDE Agent"
---

# Run Nemotron 3 Ultra free in FreeIDE Agent

FreeIDE has been inducted into the **Nemotron Coalition** of leading AI labs working with **NVIDIA** to advance open frontier foundation models. In honor of this, we've partnered with **Nebius** to provide **Nemotron 3 Ultra** free for two weeks (**June 4th – June 18th**), available through free providers like OpenRouter. Follow the instructions below to try the model in your FreeIDE Agent today.

:::info Limited-time offer
The `nvidia/nemotron-3-ultra:free` tier is available from **June 4th to June 18th**. The `:free` tag is what keeps it on the no-cost plan — pick that exact variant.
:::

Pick whichever install fits you. The **desktop app** is the easiest — no terminal required. If you live in a terminal, the **command-line** install is right below it.

## Option A — Desktop app (recommended)

The simplest path: a one-click installer with a guided, point-and-click setup. No terminal needed.

### 1. Download and install

[Download the FreeIDE Desktop installer](https://freeide-agent.freeide.dev/) for macOS or Windows, then open it. On first launch it finishes setting itself up (usually under a minute).

### 2. Connect a provider

When the app opens, you'll see a "Let's get you set up" screen. Pick a provider that offers Nemotron 3 Ultra — for example **OpenRouter** — and paste your API key (create a free key from the provider's dashboard). The app connects automatically.

### 3. Pick the free Nemotron 3 Ultra model

After connecting, the app shows a **Default model** card. Click **Change**, search for **nemotron 3 ultra**, and select the variant tagged **Free tier**:

```
nvidia/nemotron-3-ultra:free
```

The `:free` tag is what keeps it on the no-cost tier — pick that variant.

### 4. Start chatting

Click **Start chatting**. That's it — you're talking to Nemotron 3 Ultra, free.

## Option B — Command line

Prefer the terminal?

### 1. Install FreeIDE Agent

On macOS/Linux/WSL2/Android, run

```bash
curl -fsSL https://freeide-agent.freeide.dev/install.sh | bash
```

On Windows, run

```powershell
iex (irm https://freeide-agent.freeide.dev/install.ps1)
```

Prefer to review first? Download [`install.sh`](https://freeide-agent.freeide.dev/install.sh), inspect it, then run it.

After it finishes, reload your shell:

```bash
source ~/.bashrc   # or source ~/.zshrc
```

### 2. Run setup and pick a provider

```bash
freeide setup
```

When prompted, choose a provider that offers Nemotron 3 Ultra — for example **OpenRouter** — and paste your API key. Create a free key from the provider's dashboard if you don't have one yet.

### 3. Select the free Nemotron 3 Ultra model

Return to your terminal. From the model list, select:

```
nvidia/nemotron-3-ultra:free
```

The `:free` tag is what keeps it on the no-cost tier, so make sure you pick that variant.

### 4. Start chatting

Complete the remaining setup prompts, then run:

```bash
freeide
```

That's it — you're talking to Nemotron 3 Ultra, free.

## Switching to it later

Already set up with another model?

- **Desktop app:** open the model picker, search for **nemotron 3 ultra**, and select the **Free tier** variant.
- **CLI / TUI:** switch any time from inside a session with `/model nvidia/nemotron-3-ultra:free`, or run `/model` to open the picker and choose it from the list.

## Troubleshooting

- **Don't see the model in the list?** Make sure you selected a provider that offers Nemotron 3 Ultra and that your API key is valid. Re-run `freeide setup` to check or change your provider.
- **Picked the wrong variant?** Re-select `nvidia/nemotron-3-ultra:free` — the `:free` suffix is required to stay on the no-cost tier.
- **Browser didn't open / you're on a remote host (CLI)?** See [OAuth over SSH / Remote Hosts](/guides/oauth-over-ssh) for port-forwarding workarounds.

## See also

- **[Desktop App](/user-guide/desktop)** — The native one-click app (macOS, Windows, Linux)
- **[Quickstart](/getting-started/quickstart)** — Install-to-chat in under 5 minutes
