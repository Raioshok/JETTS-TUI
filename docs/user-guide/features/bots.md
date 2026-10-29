---
title: "Jetts Bots (AI Teammates)"
description: "Named AI teammates with a job, their own memory, one ongoing conversation and routines"
---

# Jetts Bots — AI teammates

A **Jetts Bot** is a named teammate you give real work to. Each Bot has:

- **A job** — plain words, like briefing a new teammate ("Draft outreach for prospects
  from my sheet; never send without my OK").
- **Its own memory** — the Bot's notes live in `~/.jettstui/bots/<id>/MEMORY.md`.
  What JettsTUI knows about *you* (`USER.md`) is shared, so every Bot knows the same user.
- **One ongoing conversation** — open the Bot and you are back in its thread, with its
  context. Compression and branches keep the Bot attached.
- **Routines** — scheduled jobs that run with the Bot's job description.

Bots live inside a profile. Profiles stay isolated from each other; Bots in the same
profile are teammates.

## Create and manage Bots

Desktop: open **Bots** from the header switcher or the command palette (⌘K → "Bots"),
then **New Bot**. **Start chat** opens the Bot's first conversation; after that the
button reads **Open chat**.

CLI:

```bash
jettstui bot create "Sales Outbound" --role "Draft outreach for prospects from my sheet; never send without my OK."
jettstui bot list
jettstui bot show sales-outbound
jettstui bot remove sales-outbound   # archives to ~/.jettstui/bots/.archive/, memory kept
```

`--model` / `--provider` pin a model for one Bot; otherwise new chats use the model
picked in the composer, then the profile default.

## Routines

Ask a Bot in its own chat to "run this every Friday" — the cron job it creates is tagged
with that Bot automatically. From the CLI:

```bash
jettstui cron create "0 9 * * 5" "Summarize this week's commits" --bot weekly-reporting
```

Routines run with the Bot's job description. Like every cron job they run without
memory, so a routine never rewrites the Bot's notes.

## Safety

Bots use the same approvals as every other chat: actions that need approval still ask
you, on every surface. A Bot's role is told to stop and ask before anything irreversible
or when it needs you to sign in somewhere.
