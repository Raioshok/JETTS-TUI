---
sidebar_position: 11
title: "ACP Editor Integration"
description: "Use FreeIDE Agent inside ACP-compatible editors such as VS Code, Zed, and JetBrains"
---

# ACP Editor Integration

FreeIDE Agent can run as an ACP server, letting ACP-compatible editors talk to FreeIDE over stdio and render:

- chat messages
- tool activity
- file diffs
- terminal commands
- approval prompts
- streamed thinking / response chunks

ACP is a good fit when you want FreeIDE to behave like an editor-native coding agent instead of a standalone CLI or messaging bot.

## What FreeIDE exposes in ACP mode

FreeIDE runs with a curated `freeide-acp` toolset designed for editor workflows. It includes:

- file tools: `read_file`, `write_file`, `patch`, `search_files`
- terminal tools: `terminal`, `process`
- web/browser tools
- memory, todo, session search
- skills
- execute_code and delegate_task
- vision

It intentionally excludes things that do not fit typical editor UX, such as messaging delivery and cronjob management.

## Installation

Install FreeIDE normally, then add the ACP extra from the install checkout:

```bash
cd ~/.freeide/freeide-agent && uv pip install -e '.[acp]'
```

This installs the `agent-client-protocol` dependency and enables:

- `freeide acp`
- `freeide-acp`
- `python -m acp_adapter`

## Launching the ACP server

Any of the following starts FreeIDE in ACP mode:

```bash
freeide acp
```

```bash
freeide-acp
```

```bash
python -m acp_adapter
```

FreeIDE logs to stderr so stdout remains reserved for ACP JSON-RPC traffic.

For non-interactive checks:

```bash
freeide acp --version
freeide acp --check
```

### Browser tools (optional)

Browser tools (`browser_navigate`, `browser_click`, etc.) depend on the
`agent-browser` npm package and Chromium, which aren't part of the Python
wheel. Install them with:

```bash
freeide acp --setup-browser           # interactive (prompts before ~400 MB download)
freeide acp --setup-browser --yes     # accept the download non-interactively
```

This is the standalone command. The terminal-auth flow (`freeide acp --setup`) also offers the browser bootstrap as a follow-up question after model selection, so most users never need to run `--setup-browser` directly.

What it does:

- Installs Node.js 22 LTS into `~/.freeide/node/` if missing
- `npm install -g agent-browser @askjo/camofox-browser` into that prefix (no sudo needed — `npm`'s `--prefix` points at the user-writable FreeIDE-managed Node)
- Installs Playwright Chromium, or uses a detected system Chrome/Chromium when available

The bootstrap is idempotent — re-running it is fast and skips work that's already done.

## Editor setup

### VS Code

Install the [ACP Client](https://marketplace.visualstudio.com/items?itemName=formulahendry.acp-client) extension.

To connect:

1. Open the ACP Client panel from the Activity Bar.
2. Select **FreeIDE Agent** from the built-in agent list.
3. Connect and start chatting.

If you want to define FreeIDE manually, add it through VS Code settings under `acp.agents`:

```json
{
  "acp.agents": {
    "FreeIDE Agent": {
      "command": "freeide",
      "args": ["acp"]
    }
  }
}
```

### Zed

Configure FreeIDE as a custom agent server in Zed settings:

1. Open the Agent Panel.
2. Add a custom agent server with the following configuration:

```json
{
  "agent_servers": {
    "freeide-agent": {
      "type": "custom",
      "command": "freeide",
      "args": ["acp"]
    }
  }
}
```

3. Start a new FreeIDE external-agent thread.

Prerequisites:

- Configure FreeIDE provider credentials first with `freeide model`, or set them in `~/.freeide/.env` / `~/.freeide/config.yaml`.

### JetBrains

Use an ACP-compatible plugin and point it at `freeide acp` or `freeide-acp`.

## Configuration and credentials

ACP mode uses the same FreeIDE configuration as the CLI:

- `~/.freeide/.env`
- `~/.freeide/config.yaml`
- `~/.freeide/skills/`
- `~/.freeide/state.db`

Provider resolution uses FreeIDE' normal runtime resolver, so ACP inherits the currently configured provider and credentials. FreeIDE also advertises a terminal auth method (`--setup`) for first-run ACP clients; this opens FreeIDE' interactive model/provider setup.

## Host integration

These variables are set by an **ACP host process** (an editor or another agent
harness) on the FreeIDE subprocess it spawns. They are not user configuration —
do not set them by hand in `.env` or `config.yaml`.

| Variable | Value | Effect |
|----------|-------|--------|
| `FREEIDE_ACP_SKIP_CONFIGURED_MCP` | `1` | Skip starting the **globally configured** MCP servers from `config.yaml` before the ACP JSON-RPC loop begins. |

FreeIDE normally starts every MCP server configured in `config.yaml` before it
enters the ACP JSON-RPC loop. A host that owns MCP itself — passing the
session's servers explicitly through `session/new` — does not need that global
startup, and an unrelated slow or interactive MCP server would otherwise delay
`initialize`. Setting the marker to exactly `1` lets such a host skip it.

Only the global `config.yaml` discovery is skipped. **MCP servers supplied by
the ACP session through `session/new` are still registered**, so a host loses
no capability it asked for. Any other value (unset, empty, `0`, `false`) keeps
the default behavior, so an unrelated truthy-looking string cannot silently
disable MCP.

## Session behavior

ACP sessions are tracked by the ACP adapter's in-memory session manager while the server is running.

Each session stores:

- session ID
- working directory
- selected model
- current conversation history
- cancel event

The underlying `AIAgent` still uses FreeIDE' normal persistence/logging paths, but ACP `list/load/resume/fork` are scoped to the currently running ACP server process.

## Working directory behavior

ACP sessions bind the editor's cwd to the FreeIDE task ID so file and terminal tools run relative to the editor workspace, not the server process cwd.

## Approvals

Dangerous terminal commands can be routed back to the editor as approval prompts. ACP approval options are simpler than the CLI flow:

- allow once
- allow always
- deny

On timeout or error, the approval bridge denies the request.

### Session-scoped edit auto-approval

ACP exposes a third tier between *allow once* and *allow always*: **Allow for session**. Picking it from the editor's permission prompt records the approval inside the current ACP session only — every subsequent matching command in that session goes through without prompting, but a new ACP session (or restarting the editor) resets the slate and re-prompts the first time.

| Option | Editor label | Scope | Persisted across restarts |
|---|---|---|---|
| `allow_once` | Allow once | This one tool call | No |
| `allow_session` | Allow for session | All matching calls in this ACP session | No — cleared when the session ends |
| `allow_always` | Allow always | All future sessions | Yes (written to the FreeIDE permanent allowlist) |
| `deny` | Deny | This one tool call | No |

`allow_session` is the right default for an editor workflow where you trust an agent for the duration of a task but don't want to grant a long-lived allowlist entry. The safety trade-off is straightforward: the broader the scope, the less the editor will interrupt you, and the more damage a misbehaving agent (or prompt injection) can do before you notice. Start with `allow_once` for unfamiliar commands; promote to `allow_session` once you've seen the agent run the same pattern correctly a few times; reserve `allow_always` for truly idempotent commands you trust forever (e.g. `git status`).

The ACP bridge maps these options onto FreeIDE' internal approval semantics — `allow_always` writes a permanent allowlist entry the same way the CLI does, while `allow_session` only affects the in-process approval cache for the current ACP session.

## Troubleshooting

### ACP agent does not appear in the editor

Check:

- For manual/local development, verify the custom `agent_servers` command points to `freeide acp`.
- FreeIDE is installed and on your PATH.
- The ACP extra is installed (`cd ~/.freeide/freeide-agent && uv pip install -e '.[acp]'`).

### ACP starts but immediately errors

Try these checks:

```bash
freeide acp --version
freeide acp --check
freeide doctor
freeide status
```

### Missing credentials

ACP mode uses FreeIDE' existing provider setup. Configure credentials with:

```bash
freeide model
```

or by editing `~/.freeide/.env`. The terminal auth flow (`freeide acp --setup`) can also trigger the interactive provider/model setup.

## See also

- [ACP Internals](../../developer-guide/acp-internals.md)
- [Provider Runtime Resolution](../../developer-guide/provider-runtime.md)
- [Tools Runtime](../../developer-guide/tools-runtime.md)
