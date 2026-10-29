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

## Give a Bot a task

On the Bots page, **Give task** hands the Bot work without opening its chat. The task
runs in the background as the next message in the Bot's own conversation, so the
result is an ordinary reply you can read, follow up on, or branch. Give it another task
while it's busy and that one queues behind the first; nothing is interrupted.

Each Bot shows **Working** while it's busy and **Needs you** when an action is waiting
for your approval. You get a notification when it finishes or needs you, with a button
that opens the chat. Several Bots can work at the same time.

Tasks run in the JettsTUI backend, so they keep going while the app is open or
`jettstui serve` is running; they stop if the backend stops.

## The Bots' computer

Give the Bots a computer of their own: on the Bots page pick a VM under **Bots'
computer** (or `jettstui bot computer <vm>`). From then on:

- `computer_use` in a Bot's chat drives that VM. A Bot asking for your desktop is
  refused, so it never moves your mouse or reads your screen.
- When a Bot needs you to sign in somewhere, it says what to sign in to and stops.
  Click **Open computer** to open the VM's window (Hyper-V uses its own console
  window; other hypervisors: open the VM from their console), sign in there, and tell
  the Bot to continue. The sign-in stays on the Bots' computer for next time.
- All Bots share the one computer, like coworkers sharing a machine.

WSL distros aren't offered: WSL shares your host's drives, so it isn't a separate
computer. A Bot's chat that was already open learns the computer's name from its next
conversation; the routing applies right away.

## Teach a Bot by showing it

Click **Teach**, say what you're about to show ("Weekly sales report from the CRM"),
then do the task once. The Bot watches by taking a screenshot whenever the screen
changes — on the Bots' computer if they have one, otherwise on your screen. It never
records keystrokes, so passwords you type are not captured.

Click **Stop & learn** when you're done, optionally with notes ("always pick last
week"). The Bot studies the screenshots with its vision tool and saves a skill named
`<bot>-<what you showed>` that it can follow next time; ask it to run that skill, or
make it a routine. A lesson stops recording by itself after 15 minutes or 120
screenshots and waits for **Stop & learn**.

Lessons are kept in `~/.jettstui/bots/<id>/lessons/` and are archived with the Bot.
They are screenshots of whatever was on screen, so delete a lesson folder if it shows
something sensitive.

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
