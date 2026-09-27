# FreeIDE Test Prompts

A copy-paste checklist to exercise every major feature/technique in FreeIDE.
Run in a wide terminal (140×40) so the resident workspace is active.

**Setup:** start `freeide`, confirm the status bar shows your model/provider.
For config-dependent tests (3, 9) edit `~/.freeide/config.yaml`, not `.env`.

---

## Token optimization

### 1. Prompt caching (cache hit)
**Paste:** `What is 2+2? Reply with just the number.` — then immediately:
`Again, what is 2+2? Reply with just the number.`

**Expect:** the second turn's `/usage` shows cached/read tokens (cheaper than turn 1).
The cache must not reset between the two turns.

### 2. Context compression (verbatim identifiers survive)
**Paste:**
```
Paste this and remember it exactly:
API_KEY=sk-abc123 var=prod_us_east_2 version=3.14.2 path=/opt/apps/gateway/main.py
Now answer: what is the version, and what is the path?
```
Then run `/compress`.

**Expect:** history collapses to a summary, but `prod_us_east_2`, `3.14.2`, and
`/opt/apps/gateway/main.py` survive verbatim. No "I don't remember".
The API key must NOT survive: the summary output is passed through
`_redact_compaction_text()`, so `sk-abc123` becomes `***` by design
(`agent/context_compressor.py:3559`). A credential surviving compaction is a
FAILURE, not a pass.

### 3. Output economics / max_tokens
**Paste:** `Summarize the Rust book in 20 words.`

**Expect:** a concise answer. To test the hard cap, set `model.max_tokens: 50` in
`config.yaml`, restart, and ask a question whose answer would exceed 50 tokens —
verify it truncates instead of running long.

### 4. Cheap-model routing (auxiliary)
**Paste:** `/compress` after a long conversation, then check `/usage`.

**Expect:** the summary run is cheap (auxiliary model), not the main model at
full-rate tokens.

### 5. Mixture-of-Agents (quality)
**Paste:**
```
/moa What's the best way to structure a Python plugin system — dynamic discovery
or an explicit registry? Give a recommendation with tradeoffs.
```

**Expect:** labelled reference blocks from multiple models, then an aggregated answer.

---

## Resident workspace (TUI)

### 6. Unread badge
**Steps:** `Ctrl+X` → `+ new session` (now 2 live). Send a long task to session 1,
switch to session 2 with `Alt+2`.

**Expect:** session 1's sidebar row shows `+N`; it clears when you `Alt+1` back.

### 7. Recency labels + Comms panel
**Expect:** the Comms panel shows the 3 most-recently-active sessions with `3m`/`2h`
ages, not the first 3 in creation order.

### 8. Waiting tag
**Steps:** create a session that ends in an approval/clarify prompt, then look at
its preview pane.

**Expect:** `⚑ needs input` text (not just a color change).

### 9. `display.resident_workspace` config
**Steps:** set `display.resident_workspace: off`, restart → expect single-transcript
layout even at 140×40. Set `on` → workspace appears even at 100×24 (with 1 live
session). `auto` → original 118×30 threshold.

### 10. Switching shortcuts
**Steps:** `Alt+1`…`Alt+9` and click-select a session.

**Expect:** `INPUT → <session>` updates, no transcript injected, no
double-highlight during the 1.5s poll.

---

## Work modes

### 11. Plan mode boundary
**Paste:** `/mode plan` then `Create a file /tmp/x.txt and write hello to it.`

**Expect:** the agent plans but does NOT create the file. Tool-level mutations are
blocked.

### 12. Accept-edits mode
**Paste:** `/mode accept-edits` then `Fix the typo in foo.py.`

**Expect:** edits auto-apply without approval prompts.

### 13. Shift+Tab cycle
**Steps:** press `Shift+Tab` repeatedly.

**Expect:** mode badge cycles Default → Accept Edits → Plan, responsive even while busy.

---

## Slash commands (curated surface)

### 14. Discovery surfaces
**Paste:** `/help` (expect 42 primary commands), then `/help all` (expect the
advanced/legacy set).

### 15. Kiro-style spec
**Paste:** `/spec quick offline-search`

**Expect:** `.freeide/specs/offline-search/` with `requirements.md`, `design.md`,
`tasks.md`.

### 16. Session resume
**Paste:** `/resume` then pick an old session.

**Expect:** full transcript restored without closing the current live session.

### 17. Health
**Paste:** `/doctor`, `/usage`, `/status`.

**Expect:** runtime diagnostics; token/cost breakdown; session state line.

---

## Model discovery + skills + other

### 18. Endpoint-authoritative models
**Paste:** `/model`

**Expect:** the live catalog from the configured provider (OpenRouter
account-aware) — no stale hardcoded preset list.

### 19. token-efficient-work skill
**Paste:**
```
Plan a large multi-file refactor and tell me your task budget and delegation split.
```

**Expect:** explicit budget, narrow delegation, concise plan — the skill's
operating loop, not a wall of text.

### 20. Skill creation
**Steps:** do a genuinely multi-step task (5+ tool calls) that succeeds.

**Expect:** an offer to save it as a skill.

### 21. Obsidian brain
**Paste:** `/brain status`

**Expect:** vault path + brain state (or a clear "not initialized" message with the
init command).

### 22. Delegation / subagents
**Paste:**
```
Research two unrelated topics — A: Python async patterns, B: SQLite WAL mode —
in parallel and report both.
```

**Expect:** two subagents dispatched in parallel, both results returned, no context
bleed between them.

---

## Quick verdict key

| Result | Meaning |
| ------ | ------- |
| Turn 2 usage shows cache reads (test 1) | prompt caching live |
| Identifiers survive `/compress` — and credentials do not (test 2) | detail-preservation and secret redaction both work |
| `+N` appears and clears (test 6) | unread tracking wired |
| `⚑ needs input` (test 8) | accessibility tag live |
| `/mode plan` blocks writes (test 11) | mode mutation boundary intact |
| `/model` shows live catalog (test 18) | endpoint discovery, no stale presets |
