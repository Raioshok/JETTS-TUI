# Discord Presence

Shows what JettsTUI is doing on your Discord profile: thinking, editing code,
running commands, waiting for your approval. It talks to the Discord desktop
app over its local IPC socket. There are no extra dependencies and no network
calls beyond the one-time Application ID check.

**Privacy:** prompts, file paths, and tool arguments are never sent. The card
shows a short verb ("Editing code"). You choose whether it also shows the
model name, the project name, and the elapsed timer.

## Working in several projects

Every session is tracked on its own, and each is named after the git repo of
its workspace (a session in `my-app/src` counts as `my-app`). When more than
one project is live, the card switches to a combined view:

```text
Playing JettsTUI
Working in 3 projects          ← also shown in member lists
Editing code · my-app          ← the session that most needs you right now
⏱ 01:12:09                     ← since you started the first one
```

- The card follows whichever session needs attention most: waiting for your
  approval, then running tools, then thinking. Ties go to the most recent.
- Hovering the art lists the projects (`JettsTUI · my-app, api, docs +1`).
- With **show project** off, the count still shows but the names don't.
- This also works across separate JettsTUI windows and terminals. Each process
  writes a heartbeat to `<JETTSTUI_HOME>/discord_presence/peers/`, and the one
  with the lowest PID shows the combined card for everyone. If that process
  exits or crashes, another one takes over within about 45 seconds.

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
  phase_badges: true                 # corner icon per phase (🧠 ⚡ ✋ 💤)
  status_display: details            # what member lists show: name | state | details
  idle_timeout_minutes: 15           # clear the card after this long idle; 0 = never
  details: ""                        # custom line 1, e.g. "Building {project}"
  state: ""                          # custom line 2, e.g. "{activity} · {model}"
  large_image: "https://…"           # https URL or an art asset key from your app
  large_text: "JettsTUI"
  small_image: ""                     # overrides the phase badge
  small_text: ""                     # defaults to the current activity
  buttons:                           # up to 2, https only
    - { label: "View on GitHub", url: "https://github.com/Raioshok/JETTS-TUI" }
```

Placeholders: `{activity}`, `{model}`, `{project}` (the focused project),
`{projects}` (up to three names, then `+N`), `{project_count}` (`3 projects`),
`{workspace}` (the project name, or the count when there are several) and
`{tool_calls}`. A field you have hidden renders as empty, and any separator
left dangling is removed.

## Behaviour

- Only the process showing the card holds a connection. If Discord isn't running, it reconnects
  with exponential backoff, from 2s up to 60s.
- Updates are coalesced. At most one is sent every 4s, which stays within
  Discord's rate limit, and unchanged state is never resent.
- Turns that come from messaging platforms (for example a Telegram gateway)
  are ignored. Only local CLI, TUI, and desktop sessions show up.
- The activity is cleared when presence is disabled, after the idle timeout,
  and when the process exits.
- Discord clients too old to know `status_display_type` reject it; the card is
  then resent without it, so you still get presence.

Phase badges are [Twemoji](https://github.com/jdecked/twemoji) graphics,
licensed CC-BY 4.0.
