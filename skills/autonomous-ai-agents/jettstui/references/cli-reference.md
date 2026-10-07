# JettsTUI CLI Reference

Live sources when anything looks stale: `jettstui --help`, `jettstui <command> --help`,
https://github.com/Raioshok/JETTS-TUI/blob/main/docs/reference/cli-commands.md

### Global Flags

```
jettstui [flags] [command]        (no subcommand = interactive chat)

  --version, -V             Show version
  -z, --oneshot PROMPT      One-shot: print ONLY the final response (for scripts/pipes)
  -m MODEL  --provider P    Model/provider override for this invocation
  -t, --toolsets LIST       Comma-separated toolsets for this invocation
  --resume, -r SESSION      Resume session by ID or title
  --continue, -c [NAME]     Resume by name, or most recent session
  --worktree, -w            Isolated git worktree mode (parallel agents)
  --skills, -s SKILL        Preload skills (comma-separate or repeat)
  --profile, -p NAME        Use a named profile
  --yolo                    Skip dangerous command approval
  --tui / --cli             Force the Ink TUI / classic REPL
  --ignore-rules            Skip AGENTS.md/SOUL.md/memory/skill injection
  --safe-mode               Disable ALL customizations (troubleshooting)
  --pass-session-id         Include session ID in system prompt
```

### Chat

```
jettstui chat [flags]
  -q, --query TEXT          Single query, non-interactive
  --image PATH              Attach a local image to a single query
  -Q, --quiet               Suppress banner, spinner, tool previews
  --checkpoints             Enable filesystem checkpoints (/rollback)
  --max-turns N             Cap tool-calling iterations
  --source TAG              Session source tag (default: cli)
```
(plus the global flags above)

### Configuration

```
jettstui setup [section]      Wizard (model|tts|terminal|gateway|tools|agent)
jettstui model                Interactive model/provider picker
jettstui fallback [add|remove|list]  Fallback provider chain
jettstui config [show|edit|get|set|unset|path|env-path|check|migrate]
jettstui login / logout       OAuth sign-in / clear stored auth
jettstui doctor [--fix]       Check dependencies and config
jettstui status [--all]       Component status
```

### Tools & Skills

```
jettstui tools [list|enable NAME|disable NAME]   Per-platform toolsets (curses UI with no args)

jettstui skills list|browse|search QUERY|inspect ID
jettstui skills install ID    Hub identifier OR a direct https://…/SKILL.md URL
jettstui skills config        Enable/disable skills per platform
jettstui skills check|update|uninstall|publish PATH
jettstui skills tap add REPO  Add a GitHub repo as a skill source
jettstui bundles              Skill bundles (one /<name> alias loads several skills)
```

### MCP Servers

```
jettstui mcp add NAME (--url or --command) | remove | list | test NAME
jettstui mcp catalog | install NAME     Curated catalog install
jettstui mcp configure NAME             Toggle tool selection
jettstui mcp serve                      Run JettsTUI as an MCP server
```
Details (transport, tool discovery, catalog): `references/native-mcp.md`.

### Gateway (Messaging Platforms)

```
jettstui gateway run|install|start|stop|restart|status|setup
```

20+ platforms: Telegram, Discord, Slack, WhatsApp (Baileys + Business Cloud API), iMessage (Photon — `jettstui photon setup`), Signal, Email, SMS, Matrix, Mattermost, Teams, LINE, SimpleX, ntfy, Google Chat, Home Assistant, DingTalk, Feishu, WeCom, Weixin, API Server, Webhooks. Open WebUI connects via the API Server adapter. Most adapters ship under `plugins/platforms/`.
Docs: https://github.com/Raioshok/JETTS-TUI/tree/main/docs/user-guide/messaging

### Sessions

```
jettstui sessions list|browse|rename ID TITLE|delete ID|export OUT|prune|stats
```

### Cron / Webhooks

```
jettstui cron list|create SCHED|edit ID|pause|resume|run ID|remove|status
    Schedules: '30m', 'every 2h', '0 9 * * *', ISO timestamp
jettstui webhook subscribe NAME|list|remove NAME|test NAME
```
Webhook payloads/routes: `references/webhooks.md`.

### Profiles

```
jettstui profile list|create NAME (--clone|--clone-all|--clone-from)|use|show|delete
jettstui profile rename A B | alias NAME | export NAME | import FILE
```

### Credentials & Pools

```
jettstui auth                 Interactive credential manager
jettstui auth add [PROVIDER]  Add OAuth or API-key credential (nous, openai-codex, qwen-oauth, …)
jettstui auth list|remove P IDX|reset PROVIDER|status
```
Multiple credentials per provider form a pool that rotates automatically and skips exhausted keys.

### Other

```
jettstui desktop / gui        Native desktop app
jettstui dashboard            Web admin panel + embedded chat (--stop / --status)
jettstui proxy                OpenAI-compatible local proxy backed by an OAuth provider
jettstui portal               Quick setup / sign in via JettsTUI Portal
jettstui kanban <verb>        Multi-agent work-queue board
jettstui project              Named multi-folder workspaces
jettstui skin list|use|set    Switch/tweak skins (see references/themes.md)
jettstui pets <verb>          Pet mascots (see references/petdex.md)
jettstui memory setup|status|off|reset   Memory provider
jettstui secrets bitwarden|onepassword   External secret stores
jettstui moa                  Mixture-of-Agents slots
jettstui hooks / security / backup / import / checkpoints / console
jettstui logs [-f] [errors]   View agent/error logs
jettstui send                 One-off message through a gateway platform
jettstui pairing / plugins / insights / journey / computer-use
jettstui acp                  ACP server (IDE integration)
jettstui completion bash|zsh|fish
jettstui update / uninstall / claw migrate
```

Plugin- and provider-supplied subcommands (e.g. `jettstui photon setup`) only appear once their plugin is installed/active.

### Where to Find Things

| Looking for... | Location |
|---|---|
| Config options | `jettstui config edit` · [Configuration docs](https://github.com/Raioshok/JETTS-TUI/blob/main/docs/user-guide/configuration.md) |
| Tools / toolsets | `jettstui tools list` · [Tools reference](https://github.com/Raioshok/JETTS-TUI/blob/main/docs/reference/tools-reference.md) |
| Skills catalog | `jettstui skills browse` · [Skills catalog](https://github.com/Raioshok/JETTS-TUI/blob/main/docs/reference/skills-catalog.md) |
| Provider setup | `jettstui model` · [Providers guide](https://github.com/Raioshok/JETTS-TUI/blob/main/docs/integrations/providers.md) |
| Env variables | `jettstui config env-path` · [Env vars reference](https://github.com/Raioshok/JETTS-TUI/blob/main/docs/reference/environment-variables.md) |
| Gateway logs | `~/.jettstui/logs/gateway.log` (or `jettstui logs`) |
| Sessions | `jettstui sessions browse` (reads state.db) |
