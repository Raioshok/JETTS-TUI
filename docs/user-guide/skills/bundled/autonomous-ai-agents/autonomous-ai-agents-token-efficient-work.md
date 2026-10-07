---
title: "Token Efficient Work"
sidebar_label: "Token Efficient Work"
description: "Plan and execute expensive or repeated agent work with explicit budgets, narrow delegation, concise reporting, persistent preferences, and resumable progress"
---

<!-- Generated from its SKILL.md source; edit the skill, not this copy. -->

# Token Efficient Work

Plan and execute expensive or repeated agent work with explicit budgets, narrow delegation, concise reporting, persistent preferences, and resumable progress.

## Skill metadata

| | |
|---|---|
| Source | Bundled (installed by default) |
| Path | `skills/autonomous-ai-agents/token-efficient-work` |
| Platforms | linux, macos, windows |

## Reference: full SKILL.md

:::info
The following is the complete skill definition that FreeIDE loads when this skill is triggered. This is what the agent sees as instructions when the skill is active.
:::

# Token-Efficient Work

Use this skill when the user asks to reduce agent cost, token usage, tool noise,
or repeated-work overhead, or when planning a large multi-step task.

## Operating loop

1. Define the outcome, exact files or systems in scope, verification, and a
   realistic token/tool-turn planning budget.
2. Search narrowly before reading broadly. Batch independent reads and checks.
3. Delegate only independent reasoning work whose parallelism or isolation is
   worth duplicating context. Use the configured delegation model and provide
   exact paths, constraints, and expected output.
4. Execute mechanical edits and verification locally. Correct a failed premise
   immediately rather than extending it.
5. Keep progress updates to decisions, completed milestones, blockers, or
   changed risk. Keep tool reports short.
6. For work likely to exceed 12 turns or span a handoff, maintain
   `.freeide-progress.md` with objective, constraints, completed work, next step,
   and verification. Delete it at completion unless retention is requested.
7. End with the outcome and evidence. Avoid repeating the transcript.

## Persistence rules

- Save stable user preferences to memory or project instructions.
- Turn a workflow into a skill only after it recurs or the user explicitly asks.
- Keep transient task facts in the progress file, not durable memory.
- Improve an existing umbrella skill instead of creating near-duplicates.

## Cost traps

- Do not ping an API merely to start or manipulate a rolling usage window.
- Do not delegate a single lookup or mechanical change.
- Do not enable plugins or toolsets speculatively.
- Do not claim savings without comparable before/after usage measurements.
- Do not use a budget as a reason to leave a repository in a broken state.

## Cost levers already wired in FreeIDE

Chinese-forum and research guidance (52pojie, linux.do, 知乎, and the
prompt-caching/compression literature) converges on a handful of techniques.
FreeIDE already implements them at the transport layer — know them so you
don't re-implement or accidentally fight them:

- **Prompt caching** — the stable system prefix plus the last messages carry
  `cache_control` breakpoints (5m/1h TTL). Keep the prefix byte-stable for the
  life of a conversation: never swap toolsets, rebuild the system prompt, or
  inject synthetic mid-conversation messages, or the cache resets and the next
  turn repays the full input.
- **Context compression** — an auxiliary (cheap) model summarizes history past
  the threshold. If you hand-roll a summary prompt, require it to keep every
  identifier verbatim (file paths, variable names, versions, command flags);
  the built-in compressor already does this, but ad-hoc summaries elsewhere
  must too, or technical details get dropped for token savings.
- **Output economics** — output tokens cost 4–8× input on most providers.
  Prefer concise final answers, respect `model.max_tokens` in config.yaml, and
  don't echo the transcript or emit filler.
- **Model routing** — mechanical subtasks, subagent delegation, and compression
  already route to the cheap auxiliary model (`auxiliary.compression`); only
  the main model does the reasoning. Don't run a big model on a lookup.
- **No cache keep-warm** — do not ping the API to refresh a rolling cache TTL;
  that is a quota-window ping and is explicitly banned, even though "keep the
  cache warm with a heartbeat" appears in the forums.
