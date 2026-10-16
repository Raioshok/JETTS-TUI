# Discord Presence

Shows what JettsTUI is doing on your Discord profile: thinking, editing code,
running commands, waiting for your approval. It talks to the Discord desktop
app over its local IPC socket. There are no extra dependencies and no network
calls beyond the one-time Application ID check.

**Privacy:** prompts, file paths, and tool arguments are never sent. The card
shows a short verb ("Editing code"). You choose whether it also shows the
model name, the project folder name, and the elapsed timer.

## Setup

1. Create an application at <https://discord.com/developers/applications>.
   Its name is what your profile shows you "Playing", so call it something like
   `JettsTUI`. You can optionally upload art assets.
2. Enable it in one of two ways:

   ```bash
   jettstui plugins enable discord-presence
   jettstui rpc setup <application-id>   # validates the ID and turns presence on
   ```

   Or, in JettsTUI Desktop, go to **Settings → Discord Presence**.

## Commands

| Command | What it does |
|---|---|
| `jettstui rpc status` | Shows config, the Discord connection, and a preview |
| `jettstui rpc on` / `off` | Turns presence on or off (off also clears the activity) |
| `jettstui rpc preset [name]` | Lists the presets, or switches to one |
| `jettstui rpc test` | Shows the preview card for 15 seconds |
| `/rpc [status\|on\|off\|preset <name>\|refresh]` | The same, from inside a session |

## Configuration (`config.yaml`)

```yaml
discord_rpc:
  enabled: true
  client_id: "123456789012345678"   # your Application ID
  preset: pairing                    # pairing | vibe_coding | autonomous | minimal
  activity_type: playing             # playing | listening | watching | competing
  show_model: true
  show_project: true
  show_tool_activity: true
  show_elapsed: true
  idle_timeout_minutes: 15           # clear the card after this long idle; 0 = never
  details: ""                        # custom line 1, e.g. "Building {project}"
  state: ""                          # custom line 2, e.g. "{activity} · {model}"
  large_image: "https://…"           # https URL or an art asset key from your app
  large_text: "JettsTUI"
  small_image: ""
  small_text: ""                     # defaults to the current activity
  buttons:                           # up to 2, https only
    - { label: "View on GitHub", url: "https://github.com/Raioshok/JETTS-TUI" }
```

Placeholders: `{activity}`, `{model}`, `{project}`, `{tool_calls}`. A field
you have hidden renders as empty, and any separator left dangling is removed.

## Behaviour

- Each process holds one connection. If Discord isn't running, it reconnects
  with exponential backoff, from 2s up to 60s.
- Updates are coalesced. At most one is sent every 4s, which stays within
  Discord's rate limit, and unchanged state is never resent.
- Turns that come from messaging platforms (for example a Telegram gateway)
  are ignored. Only local CLI, TUI, and desktop sessions show up.
- The activity is cleared when presence is disabled, after the idle timeout,
  and when the process exits.
