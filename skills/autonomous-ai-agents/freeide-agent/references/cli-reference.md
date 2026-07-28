# FreeIDE CLI Reference

Live sources when anything looks stale: `freeide --help`, `freeide <command> --help`,
https://freeide-agent.nousresearch.com/docs/reference/cli-commands

### Global Flags

```
freeide [flags] [command]        (no subcommand = interactive chat)

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
freeide chat [flags]
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
freeide setup [section]      Wizard (model|tts|terminal|gateway|tools|agent)
freeide model                Interactive model/provider picker
freeide fallback [add|remove|list]  Fallback provider chain
freeide config [show|edit|get|set|unset|path|env-path|check|migrate]
freeide login / logout       OAuth sign-in / clear stored auth
freeide doctor [--fix]       Check dependencies and config
freeide status [--all]       Component status
```

### Tools & Skills

```
freeide tools [list|enable NAME|disable NAME]   Per-platform toolsets (curses UI with no args)

freeide skills list|browse|search QUERY|inspect ID
freeide skills install ID    Hub identifier OR a direct https://…/SKILL.md URL
freeide skills config        Enable/disable skills per platform
freeide skills check|update|uninstall|publish PATH
freeide skills tap add REPO  Add a GitHub repo as a skill source
freeide bundles              Skill bundles (one /<name> alias loads several skills)
```

### MCP Servers

```
freeide mcp add NAME (--url or --command) | remove | list | test NAME
freeide mcp catalog | install NAME     Curated catalog install
freeide mcp configure NAME             Toggle tool selection
freeide mcp serve                      Run FreeIDE as an MCP server
```
Details (transport, tool discovery, catalog): `references/native-mcp.md`.

### Gateway (Messaging Platforms)

```
freeide gateway run|install|start|stop|restart|status|setup
```

20+ platforms: Telegram, Discord, Slack, WhatsApp (Baileys + Business Cloud API), iMessage (Photon — `freeide photon setup`), Signal, Email, SMS, Matrix, Mattermost, Teams, LINE, SimpleX, ntfy, Google Chat, Home Assistant, DingTalk, Feishu, WeCom, Weixin, API Server, Webhooks. Open WebUI connects via the API Server adapter. Most adapters ship under `plugins/platforms/`.
Docs: https://freeide-agent.nousresearch.com/docs/user-guide/messaging/

### Sessions

```
freeide sessions list|browse|rename ID TITLE|delete ID|export OUT|prune|stats
```

### Cron / Webhooks

```
freeide cron list|create SCHED|edit ID|pause|resume|run ID|remove|status
    Schedules: '30m', 'every 2h', '0 9 * * *', ISO timestamp
freeide webhook subscribe NAME|list|remove NAME|test NAME
```
Webhook payloads/routes: `references/webhooks.md`.

### Profiles

```
freeide profile list|create NAME (--clone|--clone-all|--clone-from)|use|show|delete
freeide profile rename A B | alias NAME | export NAME | import FILE
```

### Credentials & Pools

```
freeide auth                 Interactive credential manager
freeide auth add [PROVIDER]  Add OAuth or API-key credential (nous, openai-codex, qwen-oauth, …)
freeide auth list|remove P IDX|reset PROVIDER|status
```
Multiple credentials per provider form a pool that rotates automatically and skips exhausted keys.

### Other

```
freeide desktop / gui        Native desktop app
freeide dashboard            Web admin panel + embedded chat (--stop / --status)
freeide proxy                OpenAI-compatible local proxy backed by an OAuth provider
freeide portal               Quick setup / sign in via Nous Portal
freeide kanban <verb>        Multi-agent work-queue board
freeide project              Named multi-folder workspaces
freeide skin list|use|set    Switch/tweak skins (see references/themes.md)
freeide pets <verb>          Pet mascots (see references/petdex.md)
freeide memory setup|status|off|reset   Memory provider
freeide secrets bitwarden|onepassword   External secret stores
freeide moa                  Mixture-of-Agents slots
freeide hooks / security / backup / import / checkpoints / console
freeide logs [-f] [errors]   View agent/error logs
freeide send                 One-off message through a gateway platform
freeide pairing / plugins / insights / journey / computer-use
freeide acp                  ACP server (IDE integration)
freeide completion bash|zsh|fish
freeide update / uninstall / claw migrate
```

Plugin- and provider-supplied subcommands (e.g. `freeide photon setup`) only appear once their plugin is installed/active.

### Where to Find Things

| Looking for... | Location |
|---|---|
| Config options | `freeide config edit` · [Configuration docs](https://freeide-agent.nousresearch.com/docs/user-guide/configuration) |
| Tools / toolsets | `freeide tools list` · [Tools reference](https://freeide-agent.nousresearch.com/docs/reference/tools-reference) |
| Skills catalog | `freeide skills browse` · [Skills catalog](https://freeide-agent.nousresearch.com/docs/reference/skills-catalog) |
| Provider setup | `freeide model` · [Providers guide](https://freeide-agent.nousresearch.com/docs/integrations/providers) |
| Env variables | `freeide config env-path` · [Env vars reference](https://freeide-agent.nousresearch.com/docs/reference/environment-variables) |
| Gateway logs | `~/.freeide/logs/gateway.log` (or `freeide logs`) |
| Sessions | `freeide sessions browse` (reads state.db) |
