# Jetts-TUI

Jetts-TUI is a terminal-first AI workspace with a full-screen TUI, an agent runtime, memory, subagents, scheduled work, and messaging integrations. The same runtime also powers the desktop and web surfaces in this repository.

Choose a supported provider or your own endpoint with `jetts-tui model`. Existing provider and hosted-service integrations remain available; this rebrand does not redirect those connections.

The code is MIT licensed. The copyright notice and third-party attributions remain in [LICENSE](LICENSE) and the relevant dependency licenses.

<table>
<tr><td><b>A real terminal interface</b></td><td>Full TUI with multiline editing, slash-command autocomplete, conversation history, interrupt-and-redirect, and streaming tool output.</td></tr>
<tr><td><b>Lives where you do</b></td><td>Telegram, Discord, Slack, WhatsApp, Signal, and CLI — all from a single gateway process. Voice memo transcription, cross-platform conversation continuity.</td></tr>
<tr><td><b>A closed learning loop</b></td><td>Agent-curated memory with periodic nudges. Autonomous skill creation after complex tasks. Skills self-improve during use. FTS5 session search with LLM summarization for cross-session recall. <a href="https://github.com/plastic-labs/honcho">Honcho</a> dialectic user modeling. Compatible with the <a href="https://agentskills.io">agentskills.io</a> open standard.</td></tr>
<tr><td><b>Scheduled automations</b></td><td>Built-in cron scheduler with delivery to any platform. Daily reports, nightly backups, weekly audits — all in natural language, running unattended.</td></tr>
<tr><td><b>Delegates and parallelizes</b></td><td>Spawn isolated subagents for parallel workstreams. Write Python scripts that call tools via RPC, collapsing multi-step pipelines into zero-context-cost turns.</td></tr>
<tr><td><b>Runs anywhere, not just your laptop</b></td><td>Six terminal backends — local, Docker, SSH, Singularity, Modal, and Daytona. Daytona and Modal offer serverless persistence — your agent's environment hibernates when idle and wakes on demand, costing nearly nothing between sessions. Run it on a $5 VPS or a GPU cluster.</td></tr>
<tr><td><b>Research-ready</b></td><td>Batch trajectory generation, trajectory compression for training the next generation of tool-calling models.</td></tr>
</table>

---

## Install from this repository

Clone or download this repository, then run the local setup script. Do not use installers hosted on a different project's domain for a Jetts-TUI install.

### Linux, macOS, or WSL2

Use the local-checkout setup script for your platform. It installs dependencies,
reuses the local virtual environment on later runs, exposes `jetts-tui` on PATH,
syncs bundled skills, and opens the provider/model wizard.

```bash
bash setup-jetts-tui.sh
```

### Native Windows PowerShell

```powershell
.\setup-jetts-tui.ps1
```

If local script execution is restricted, use the policy-scoped form (it changes
nothing outside this one process):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup-jetts-tui.ps1
```

Pass `--skip-setup` on Linux or `-SkipSetup` on Windows to postpone the wizard.
Pass `--recreate` or `-Recreate` only when you intentionally want to rebuild
the checkout's virtual environment.

After installation:

```bash
source ~/.bashrc    # reload shell (or: source ~/.zshrc)
jetts-tui              # start chatting!
```

### Troubleshooting

#### Windows Defender or antivirus flags `uv.exe` as malware

If your antivirus quarantines `uv.exe` from the Jetts-TUI `bin` folder (`%LOCALAPPDATA%\freeide\bin\uv.exe`), do not assume the detection is a false positive. Jetts-TUI uses Astral's `uv` to manage its Python environment; verify the specific binary before restoring or running it.

**To verify your copy is authentic:**

```powershell
# Install GitHub CLI if needed
winget install --id GitHub.cli

# Login to GitHub
gh auth login

# Run verification
$uv = "$env:LOCALAPPDATA\freeide\bin\uv.exe"
$ver = (& $uv --version).Split(' ')[1]
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$zip = "$env:TEMP\uv.zip"
Invoke-WebRequest "https://github.com/astral-sh/uv/releases/download/$ver/uv-x86_64-pc-windows-msvc.zip" -OutFile $zip -UseBasicParsing
gh attestation verify $zip --repo astral-sh/uv
Expand-Archive $zip "$env:TEMP\uv_x" -Force
(Get-FileHash "$env:TEMP\uv_x\uv.exe").Hash -eq (Get-FileHash $uv).Hash
```

If attestation says "Verification succeeded" and the last line prints `True`, you're good.

If verification fails or you cannot verify the binary, leave it quarantined and report the installer source and detection details. Avoid excluding the entire Jetts-TUI directory from antivirus scanning.

For more context, see the upstream Astral reports: [astral-sh/uv#13553](https://github.com/astral-sh/uv/issues/13553), [astral-sh/uv#15011](https://github.com/astral-sh/uv/issues/15011), [astral-sh/uv#10079](https://github.com/astral-sh/uv/issues/10079).

---

## Getting Started

```bash
jetts-tui              # Interactive CLI — start a conversation
jetts-tui model        # Choose your LLM provider and model
jetts-tui tools        # Configure which tools are enabled
jetts-tui config set   # Set individual config values
jetts-tui config get   # Print individual config values
jetts-tui gateway      # Start the messaging gateway (Telegram, Discord, etc.)
jetts-tui setup        # Run the full setup wizard (configures everything at once)
jetts-tui claw migrate # Migrate from OpenClaw (if coming from OpenClaw)
jetts-tui update       # Update to the latest version
jetts-tui doctor       # Diagnose any issues
```

📖 **[Full documentation →](website/docs/)**

---

## Optional Portal integration

Jetts-TUI supports an existing subscription-backed [Portal service](https://portal.freeide.dev) alongside direct provider API keys. The Portal is externally hosted; Jetts-TUI does not operate or rebrand that service.

- **300+ models** — pick any of them with `/model <name>`
- **Tool Gateway** — web search (Firecrawl), image generation (FAL), text-to-speech (OpenAI), cloud browser (Browser Use), all routed through your sub. No extra accounts.

One command from a fresh install:

```bash
jetts-tui setup --portal
```

That logs you in via OAuth, sets Jetts-TUI as your provider, and turns on the Tool Gateway. Check what's wired up any time with `jetts-tui portal info`. Full details on the [Tool Gateway docs page](website/docs/user-guide/features/tool-gateway).

You can still bring your own keys per-tool whenever you want — the gateway is per-backend, not all-or-nothing.

---

## CLI vs Messaging Quick Reference

Jetts-TUI has two entry points: start the terminal UI with `jetts-tui`, or run the gateway and talk to it from Telegram, Discord, Slack, WhatsApp, Signal, or Email. Once you're in a conversation, many slash commands are shared across both interfaces.

| Action                         | CLI                                           | Messaging platforms                                                              |
| ------------------------------ | --------------------------------------------- | -------------------------------------------------------------------------------- |
| Start chatting                 | `jetts-tui`                                      | Run `jetts-tui gateway setup` + `jetts-tui gateway start`, then send the bot a message |
| Start fresh conversation       | `/new` or `/reset`                            | `/new` or `/reset`                                                               |
| Change model                   | `/model [provider:model]`                     | `/model [provider:model]`                                                        |
| Set a personality              | `/personality [name]`                         | `/personality [name]`                                                            |
| Retry or undo the last turn    | `/retry`, `/undo`                             | `/retry`, `/undo`                                                                |
| Compress context / check usage | `/compress`, `/usage`, `/insights [--days N]` | `/compress`, `/usage`, `/insights [days]`                                        |
| Browse skills                  | `/skills` or `/<skill-name>`                  | `/<skill-name>`                                                                  |
| Interrupt current work         | `Ctrl+C` or send a new message                | `/stop` or send a new message                                                    |
| Platform-specific status       | `/platforms`                                  | `/status`, `/sethome`                                                            |

For the full command lists, see the [CLI guide](website/docs/user-guide/cli) and the [Messaging Gateway guide](website/docs/user-guide/messaging).

---

## Documentation

The documentation source is in **[website/docs](website/docs/)**:

| Section                                                                                             | What's Covered                                             |
| --------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| [Quickstart](website/docs/getting-started/quickstart)                 | Install → setup → first conversation in 2 minutes          |
| [CLI Usage](website/docs/user-guide/cli)                              | Commands, keybindings, personalities, sessions             |
| [Configuration](website/docs/user-guide/configuration)                | Config file, providers, models, all options                |
| [Messaging Gateway](website/docs/user-guide/messaging)                | Telegram, Discord, Slack, WhatsApp, Signal, Home Assistant |
| [Security](website/docs/user-guide/security)                          | Command approval, DM pairing, container isolation          |
| [Tools & Toolsets](website/docs/user-guide/features/tools)            | 80+ tools, toolset system, terminal backends               |
| [Skills System](website/docs/user-guide/features/skills)              | Procedural memory, Skills Hub, creating skills             |
| [Memory](website/docs/user-guide/features/memory)                     | Persistent memory, user profiles, best practices           |
| [MCP Integration](website/docs/user-guide/features/mcp)               | Connect any MCP server for extended capabilities           |
| [Cron Scheduling](website/docs/user-guide/features/cron)              | Scheduled tasks with platform delivery                     |
| [Context Files](website/docs/user-guide/features/context-files)       | Project context that shapes every conversation             |
| [Architecture](website/docs/developer-guide/architecture)             | Project structure, agent loop, key classes                 |
| [Contributing](website/docs/developer-guide/contributing)             | Development setup, PR process, code style                  |
| [CLI Reference](website/docs/reference/cli-commands)                  | All commands and flags                                     |
| [Environment Variables](website/docs/reference/environment-variables) | Complete env var reference                                 |

---

## Migrating from OpenClaw

If you're coming from OpenClaw, Jetts-TUI can automatically import your settings, memories, skills, and API keys.

**During first-time setup:** The setup wizard (`jetts-tui setup`) automatically detects `~/.openclaw` and offers to migrate before configuration begins.

**Anytime after install:**

```bash
jetts-tui claw migrate              # Interactive migration (full preset)
jetts-tui claw migrate --dry-run    # Preview what would be migrated
jetts-tui claw migrate --preset user-data   # Migrate without secrets
jetts-tui claw migrate --overwrite  # Overwrite existing conflicts
```

What gets imported:

- **SOUL.md** — persona file
- **Memories** — MEMORY.md and USER.md entries
- **Skills** — user-created skills → `~/.freeide/skills/openclaw-imports/`
- **Command allowlist** — approval patterns
- **Messaging settings** — platform configs, allowed users, working directory
- **API keys** — allowlisted secrets (Telegram, OpenRouter, OpenAI, Anthropic, ElevenLabs)
- **TTS assets** — workspace audio files
- **Workspace instructions** — AGENTS.md (with `--workspace-target`)

See `jetts-tui claw migrate --help` for all options, or use the `openclaw-migration` skill for an interactive agent-guided migration with dry-run previews.

---

## Contributing

We welcome contributions! See the [Contributing Guide](website/docs/developer-guide/contributing) for development setup, code style, and PR process.

Quick start for contributors from a local checkout:

```bash
bash setup-jetts-tui.sh --skip-setup
uv pip install -e ".[all,dev]"
scripts/run_tests.sh
```

Manual clone fallback (for throwaway clones/CI where you intentionally do not
want the managed install layout):

Create the venv outside the cloned source tree — a venv inside the directory
the agent operates from can be wiped by a relative-path command the agent runs
against its own checkout, destroying the running runtime mid-session.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv ~/.freeide/venvs/freeide-dev --python 3.11
source ~/.freeide/venvs/freeide-dev/bin/activate
uv pip install -e ".[all,dev]"
scripts/run_tests.sh
```

---

## License

MIT — see [LICENSE](LICENSE).
