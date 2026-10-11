---
title: Orchestrator
description: Run a task through a team of models — a planner, an executor, a reviewer and a security & quality verifier, each on its own model.
sidebar_label: Orchestrator
---

# Orchestrator

The orchestrator runs one task through a fixed team of subagents, each on the
model you choose for its role:

| Role | What it does |
|------|--------------|
| **Planner** | Investigates and writes a step-by-step plan. Never edits files. |
| **Executor** | Follows the plan, makes the changes and runs the checks. |
| **Reviewer** | Reviews the changes for bugs and missed requirements. |
| **Security & quality** | Checks for security problems, failing tests/lint and missing error handling. |

The reviewer and the verifier run in parallel after the executor and must end
with `VERDICT: APPROVED` or `VERDICT: CHANGES_REQUESTED`. Requested changes go
back to the executor for another round, up to `max_review_rounds` times; the
flow then reports every stage's model, status and findings.

## Desktop

Open **Orchestrator** in the sidebar (or the command palette):

1. Turn on **Enable orchestrator**.
2. Pick a model per role, or leave it on **Auto**.
3. Describe a task and press **Run in new chat**.

The run happens in a normal chat, so subagent progress shows in the transcript
and the Agents panel.

## Auto model selection

A role left on Auto gets a model from your configured providers, scored with
models.dev metadata (reasoning support, tool calling, price tier as a strength
signal, recency) and a name-based fallback. The planner and reviewers favour
strong reasoning models; the executor favours strong coding models. The reviewer
and the verifier prefer a *different model family* than the executor, so the
review is independent of the model that wrote the code. Models that cannot call
tools are never picked. With no other models configured, every role uses the
chat's current model.

## Configuration

The desktop page writes this section of `config.yaml`; you can also edit it by
hand:

```yaml
orchestrator:
  enabled: true
  max_review_rounds: 2        # fix rounds after the first review (0–5)
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
[`delegation`](./delegation.md) settings.
