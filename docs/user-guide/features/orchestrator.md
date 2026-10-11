---
title: Orchestrator
description: Run a task through a team of models working at the same time — a planner, an executor, a reviewer and a security & quality verifier that cross-check each other.
sidebar_label: Orchestrator
---

# Orchestrator

The orchestrator runs one task through a fixed team of subagents, each on the
model you choose for its role. All of them run **at the same time** and check
each other's work as it happens:

| Role | While the team works | When the round is judged |
|------|----------------------|--------------------------|
| **Planner** | Drafts the plan early and refines it live; flags where the executor deviates. | Checks every requirement and plan step was implemented. |
| **Executor** | Builds from the plan as it fills in, posts progress, fixes early findings. | — |
| **Reviewer** | Gathers what correctness requires and flags bugs as they appear. | Judges correctness of the final changes. |
| **Security & quality** | Baselines tests and lint, watches security-sensitive spots. | Re-runs the checks and judges security & quality. |

## How a round works

1. **Work** — all four agents start together. They coordinate through a shared
   *board*: a directory with one markdown file per role
   (`<JETTSTUI_HOME>/orchestrator/runs/<run id>/`). Each agent writes only its
   own file and reads the others', so the executor sees the plan and early
   findings while it works, and the reviewers follow its progress.
2. **Verify** — the reviewer, the security & quality verifier and the planner
   judge the final state in parallel. Each ends with `VERDICT: APPROVED` or
   `VERDICT: CHANGES_REQUESTED`.
3. If any of them requests changes, the findings start another round: the
   executor checks each finding against the code before fixing it (and says so
   on the board when it disagrees), the planner revises the plan, and the
   reviewers gather what they need to confirm the fix. This repeats up to
   `max_review_rounds` extra rounds; the flow then reports every stage's model,
   status and findings.

The last eight boards are kept so you can read what the agents told each other.
The shared board needs a local terminal backend; on remote backends the agents
still get each other's reports between phases.

## Desktop

Open **Orchestrator** in the sidebar (or the command palette):

1. Turn on **Enable orchestrator**.
2. Pick a model per role, or leave it on **Auto**, and choose the **Auto
   balance**.
3. Describe a task and press **Run in new chat**.

The **Flow** sidebar opens beside the chat and follows the run live: each
agent's model and price tier, what it is doing right now, its verdict, a
progress bar per round and phase, and a timeline of every stage. Toggle it with
**Toggle orchestrator flow** in the command palette. When the agent starts a
flow on its own, a notification offers to open the sidebar instead of opening it
for you.

## Auto model selection

A role left on Auto gets a model from your configured providers, scored by
*value*: estimated quality for the role minus a cost penalty. Quality comes from
models.dev metadata — price tier as a capability signal with diminishing
returns, reasoning and tool-calling support, context window, recency — with a
name-based fallback; the planner and reviewers weight reasoning, the executor
weights coding fit. The cost penalty grows faster than price and is weighted by
how many tokens each role burns (the executor most), so every role trades cost
against quality.

`auto_balance` sets the trade-off:

| Balance | Picks |
|---------|-------|
| `economy` | The cheapest models that can still do each role well. |
| `balanced` (default) | The best quality for the cost; premium models only where they clearly pay off. |
| `quality` | The strongest model for every role, whatever it costs. |

The reviewer and the verifier prefer a different model *lineage* than the
executor (Claude, GPT and Gemini are different lineages; two Claude models are
not), trading down a little for independence when a close alternative exists.
Models that cannot call tools are never picked. With no other models
configured, every role uses the chat's current model.

## Configuration

The desktop page writes this section of `config.yaml`; you can also edit it by
hand:

```yaml
orchestrator:
  enabled: true
  max_review_rounds: 2        # extra rounds after the first verification (0–5)
  auto_balance: balanced      # economy | balanced | quality
  roles:
    planner:  {provider: "", model: ""}            # empty model = Auto
    executor: {provider: anthropic, model: claude-sonnet-4}
    reviewer: {provider: gemini, model: gemini-2.5-pro}
    verifier: {provider: "", model: ""}
```

When `enabled` is true the agent gets the `orchestrate` tool, so you can also
ask for it in any chat ("orchestrate adding a dark mode toggle"). It is off by
default and adds nothing to the tool list until enabled. Subagents never get the
tool, so flows cannot nest. Stage limits (iterations, timeouts) follow the
[`delegation`](./delegation.md) settings. Because four agents run at once, a
round costs roughly as much as four delegated subagents — `economy` keeps that
down.
