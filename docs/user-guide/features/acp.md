---
sidebar_position: 11
title: "ACP Editor Integration"
description: "Use JettsTUI inside ACP-compatible editors such as VS Code, Zed, and JetBrains"
---

# ACP Editor Integration

JettsTUI can run as an ACP server, letting ACP-compatible editors talk to JettsTUI over stdio and render:

- chat messages
- tool activity
- file diffs
- terminal commands
- approval prompts
- streamed thinking / response chunks

ACP is a good fit when you want JettsTUI to behave like an editor-native coding agent instead of a standalone CLI or messaging bot.

## What JettsTUI exposes in ACP mode

JettsTUI runs with a curated `jettstui-acp` toolset designed for editor workflows. It includes:

- file tools: `read_file`, `write_file`, `patch`, `search_files`
- terminal tools: `terminal`, `process`
- web/browser tools
- memory, todo, session search
- skills
- execute_code and delegate_task
- vision

It intentionally excludes things that do not fit typical editor UX, such as messaging delivery and cronjob management.

## Installation

Install JettsTUI normally, then add the ACP extra from the install checkout:

```bash
cd ~/.jettstui/jettstui && uv pip install -e '.[acp]'
```

This installs the `agent-client-protocol` dependency and enables:

- `jettstui acp`
- `jettstui-acp`
- `python -m acp_adapter`

## Launching the ACP server

Any of the following starts JettsTUI in ACP mode:

```bash
jettstui acp
```

```bash
jettstui-acp
```

```bash
python -m acp_adapter
```

JettsTUI logs to stderr so stdout remains reserved for ACP JSON-RPC traffic.

For non-interactive checks:

```bash
jettstui acp --version
jettstui acp --check
```

### Browser tools (optional)

Browser tools (`browser_navigate`, `browser_click`, etc.) depend on the
`agent-browser` npm package and Chromium, which aren't part of the Python
wheel. Install them with:

```bash
jettstui acp --setup-browser           # interactive (prompts before ~400 MB download)
jettstui acp --setup-browser --yes     # accept the download non-interactively
```

This is the standalone command. The terminal-auth flow (`jettstui acp --setup`) also offers the browser bootstrap as a follow-up question after model selection, so most users never need to run `--setup-browser` directly.

What it does:

- Installs Node.js 22 LTS into `~/.jettstui/node/` if missing
- `npm install -g agent-browser @askjo/camofox-browser` into that prefix (no sudo needed — `npm`'s `--prefix` points at the user-writable JettsTUI-managed Node)
- Installs Playwright Chromium, or uses a detected system Chrome/Chromium when available

The bootstrap is idempotent — re-running it is fast and skips work that's already done.

## Editor setup

### VS Code

Install the [ACP Client](https://marketplace.visualstudio.com/items?itemName=formulahendry.acp-client) extension.

To connect:

1. Open the ACP Client panel from the Activity Bar.
2. Select **JettsTUI** from the built-in agent list.
3. Connect and start chatting.

If you want to define JettsTUI manually, add it through VS Code settings under `acp.agents`:

```json
{
  "acp.agents": {
    "JettsTUI": {
      "command": "jettstui",
      "args": ["acp"]
    }
  }
}
```

### Zed

Configure JettsTUI as a custom agent server in Zed settings:

1. Open the Agent Panel.
2. Add a custom agent server with the following configuration:

```json
{
  "agent_servers": {
    "jettstui": {
      "type": "custom",
      "command": "jettstui",
      "args": ["acp"]
    }
  }
}
```

3. Start a new JettsTUI external-agent thread.

Prerequisites:

- Configure JettsTUI provider credentials first with `jettstui model`, or set them in `~/.jettstui/.env` / `~/.jettstui/config.yaml`.

### JetBrains

Use an ACP-compatible plugin and point it at `jettstui acp` or `jettstui-acp`.

## Configuration and credentials

ACP mode uses the same JettsTUI configuration as the CLI:

- `~/.jettstui/.env`
- `~/.jettstui/config.yaml`
- `~/.jettstui/skills/`
- `~/.jettstui/state.db`

Provider resolution uses JettsTUI' normal runtime resolver, so ACP inherits the currently configured provider and credentials. JettsTUI also advertises a terminal auth method (`--setup`) for first-run ACP clients; this opens JettsTUI' interactive model/provider setup.

## Host integration

These variables are set by an **ACP host process** (an editor or another agent
harness) on the JettsTUI subprocess it spawns. They are not user configuration —
do not set them by hand in `.env` or `config.yaml`.

| Variable | Value | Effect |
|----------|-------|--------|
| `JETTSTUI_ACP_SKIP_CONFIGURED_MCP` | `1` | Skip starting the **globally configured** MCP servers from `config.yaml` before the ACP JSON-RPC loop begins. |

JettsTUI normally starts every MCP server configured in `config.yaml` before it
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

The underlying `AIAgent` still uses JettsTUI' normal persistence/logging paths, but ACP `list/load/resume/fork` are scoped to the currently running ACP server process.

## Working directory behavior

ACP sessions bind the editor's cwd to the JettsTUI task ID so file and terminal tools run relative to the editor workspace, not the server process cwd.

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
| `allow_always` | Allow always | All future sessions | Yes (written to the JettsTUI permanent allowlist) |
| `deny` | Deny | This one tool call | No |

`allow_session` is the right default for an editor workflow where you trust an agent for the duration of a task but don't want to grant a long-lived allowlist entry. The safety trade-off is straightforward: the broader the scope, the less the editor will interrupt you, and the more damage a misbehaving agent (or prompt injection) can do before you notice. Start with `allow_once` for unfamiliar commands; promote to `allow_session` once you've seen the agent run the same pattern correctly a few times; reserve `allow_always` for truly idempotent commands you trust forever (e.g. `git status`).

The ACP bridge maps these options onto JettsTUI' internal approval semantics — `allow_always` writes a permanent allowlist entry the same way the CLI does, while `allow_session` only affects the in-process approval cache for the current ACP session.

## Troubleshooting

### ACP agent does not appear in the editor

Check:

- For manual/local development, verify the custom `agent_servers` command points to `jettstui acp`.
- JettsTUI is installed and on your PATH.
- The ACP extra is installed (`cd ~/.jettstui/jettstui && uv pip install -e '.[acp]'`).

### ACP starts but immediately errors

Try these checks:

```bash
jettstui acp --version
jettstui acp --check
jettstui doctor
jettstui status
```

### Missing credentials

ACP mode uses JettsTUI' existing provider setup. Configure credentials with:

```bash
jettstui model
```

or by editing `~/.jettstui/.env`. The terminal auth flow (`jettstui acp --setup`) can also trigger the interactive provider/model setup.

## See also

- [ACP Internals](../../developer-guide/acp-internals.md)
- [Provider Runtime Resolution](../../developer-guide/provider-runtime.md)
- [Tools Runtime](../../developer-guide/tools-runtime.md)
