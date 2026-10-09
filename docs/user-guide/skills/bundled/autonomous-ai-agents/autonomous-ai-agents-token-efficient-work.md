---
title: "Token Efficient Work"
sidebar_label: "Token Efficient Work"
description: "Measures and cuts token cost of long agent work"
---

<!-- Generated from its SKILL.md source; edit the skill, not this copy. -->

# Token Efficient Work

Measures and cuts token cost of long agent work.

## Skill metadata

| | |
|---|---|
| Source | Bundled (installed by default) |
| Path | `skills/autonomous-ai-agents/token-efficient-work` |
| Version | `2.0.0` |
| Author | Raioshok (JettsTUI) |
| License | MIT |
| Platforms | linux, macos, windows |

## Reference: full SKILL.md

:::info
The following is the complete skill definition that JettsTUI loads when this skill is triggered. This is what the agent sees as instructions when the skill is active.
:::

# Token-Efficient Work Skill

Plans large or repeated work so it spends fewer tokens, and proves any saving
with JettsTUI's own usage instruments. It does not change models or providers
for the user, and never trades correctness for a smaller bill.

## When to Use

- The user asks to reduce cost, token usage, or rate-limit pressure.
- A task will clearly span many turns, files, or subagents.
- `/usage` shows the context filling up or compressions repeating.

Not for one-off questions: answering directly is already the cheapest path.

## Prerequisites

None. Every instrument below ships with JettsTUI and runs offline except
`/usage`, which reads the live session.

## How to Run

1. Measure the fixed per-call budget: `jettstui prompt-size` (add
   `--platform telegram` etc. for other surfaces).
2. Measure the session: run `/usage` in the conversation.
3. Plan, apply the levers below, then measure again the same way.

## Quick Reference

| Instrument | What it tells you |
| --- | --- |
| `jettstui prompt-size` | Bytes of system prompt, context files, skills index, and each toolset's schemas sent on every call |
| `/usage` | Session input (uncached), prompt total, output, current context %, compressions |
| `jettstui insights --days 7` | Tokens per model, platform, and tool over a period |

Cached share of a session ≈ `1 − input tokens ÷ prompt tokens (total)` from
`/usage`. A low share on a long conversation means the cached prefix keeps
breaking.

| Lever | Setting | Trade-off |
| --- | --- | --- |
| Drop unused toolsets | `jettstui tools` | Removed tools are unavailable |
| Defer MCP/plugin tools | `tools.tool_search.enabled` (default `auto`) | One extra lookup call when a deferred tool is needed |
| Cap project docs | `context_file_max_chars` | Truncated AGENTS.md guidance |
| Earlier compression | `compression.threshold`, `compression.threshold_tokens` | Older detail summarized sooner |
| Prune old tool output | `compression.proactive_prune_tokens` (e.g. `48000`) | Each prune rewrites history, so the cache misses once |
| Cheap summarizer | `auxiliary.compression.model` | Summary quality |

## Procedure

1. State the outcome, the files or systems in scope, how it will be verified,
   and a realistic tool-turn budget.
2. Take the "before" numbers from How to Run.
3. Search narrowly before reading broadly: `search_files` with exact patterns,
   `read_file` with targeted line ranges, batched independent calls.
4. Delegate with `delegate_task` only for independent reasoning work whose
   parallelism or context isolation repays the duplicated prompt. Do
   mechanical edits and verification yourself.
5. Keep the conversation's prefix byte-stable: do not ask to swap toolsets,
   reload skills, or rebuild the system prompt mid-conversation.
6. For work over ~12 turns or crossing a handoff, keep `.jettstui-progress.md`
   with objective, constraints, done, next step, and verification. Delete it
   when finished unless the user wants it kept.
7. Report the outcome and evidence once. Do not restate the transcript.
8. Take the "after" numbers and compare like with like.

## Pitfalls

- Do not claim a saving without before/after numbers from the same
  instrument on comparable work.
- Do not ping the API to keep a cache or rate-limit window warm; that spends
  quota without advancing the task.
- Do not enable plugins or toolsets speculatively; every tool schema is sent
  on every call.
- Do not create a near-duplicate skill; improve the existing umbrella skill.
  Every skill adds an index line to every request.
- Hand-written summaries must keep identifiers verbatim (paths, names,
  versions, flags), as the built-in compressor does.
- A budget is never a reason to leave the repository broken.

## Verification

- The "after" measurement shows the targeted number moved (smaller fixed
  budget in `jettstui prompt-size`, higher cached share or fewer compressions
  in `/usage`).
- The task's own checks (tests, lint, build) still pass.
- `.jettstui-progress.md` is gone unless the user asked to keep it.
