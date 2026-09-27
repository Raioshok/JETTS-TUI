# Jetts-TUI busy-workspace smoke test

Run this in a terminal at **120 columns × 32 rows or larger** with `jetts-tui`.
The fast automated check is `cd ui-tui; npm test -- residentBusySmoke.test.tsx residentWorkspace.test.tsx`.
The checks below exercise the real TUI, gateway, keyboard, and agent loop.

## 1. Busy layout and input

Paste this into the TUI:

```text
!node ui-tui/scripts/tui-busy-smoke.mjs
```

While it runs:

1. Confirm the session row, `＋ new session`, and Comms panel stay visible in the sidebar.
2. Confirm `INPUT → <current session>` and the editable prompt remain visible at the bottom.
3. Type `draft while busy` without sending it. The text must remain visible while output/status updates occur.
4. Press `Ctrl+X`. The session picker must open and close with `Esc`, preserving the draft.
5. Scroll the transcript, then click the input. The cursor must remain in the composer rather than inside the transcript.
6. After the command finishes, send the draft. It must arrive exactly once.

This script is read-only and finishes after 20 seconds. The TUI rejects inline `node -e` commands through its command guard, so use the file path above. If Node is unavailable in the agent's shell, use a trusted local command that runs for roughly 20 seconds and prints a final line.

## 2. Independent sessions

Press `Ctrl+X`, create a second live session, and send `Reply only: session two` to it. The sidebar must show **2 live sessions**. Press `Alt+1`, then `Alt+2`; the `INPUT →` label and full transcript must follow the selected session. The other session must stay live. A one-session sidebar is correct when no second live session has been created.

## 3. Child agents inside one session

In one session, send this read-only prompt:

```text
Run three independent read-only subagent checks in parallel. Ask one child to inspect the TUI resize path, one to inspect live-session switching, and one to inspect the busy composer input path. Each child should report the exact file it read and one concrete finding. Do not edit files. Wait for all three and summarize their findings briefly.
```

While the children run, `CHILD AGENTS` must appear beneath the live-session list, with a running count and each child's goal. The Comms area should show their latest activity. Click a child row or the section heading; the `/agents` overlay must open. In that overlay, arrows select a child, `Enter` opens details, `p` pauses new spawning, `x` interrupts the selected child, `X` interrupts its subtree, and `q` returns to chat. Only use `x`/`X` if interrupt behavior is the part being tested.

Child agents belong to the parent session. They are **not** additional live sessions or independent `Alt+N` input targets. To give an agent its own prompt and composer target, create another live session as in step 2.

## 4. Resize and recovery

During a busy turn, resize from 120×32 to about 100×24 and back. The sidebar should disappear and return without losing the draft, hiding the composer, closing live sessions, or duplicating the latest assistant output. Press `Shift+Tab` once: the work-mode indicator should change. Switch away from a busy session and back: its in-flight output and status should rehydrate.

## Pass criteria

- No overlapping or clipped sidebar, transcript, status, or composer text.
- Busy input accepts typing and submits exactly once.
- `Ctrl+X`, `Esc`, mouse selection, and `Alt+1…9` work during active output.
- Live sessions and child agents are counted separately and remain visible in their respective sections.
- The `/agents` overlay exposes child controls without trapping the user there.
- Resize and session switching preserve the draft and active work.

For a failure report, record the terminal name, terminal dimensions, active model/provider, the step that failed, and a screenshot. `jetts-tui logs --level warning` may contain the matching gateway error; redact secrets before sharing logs.
