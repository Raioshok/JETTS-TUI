# Spec-driven development

A spec turns a feature idea into three documents the agent writes and you
approve one phase at a time, then the agent implements it task by task.
Specs live in the workspace, in the widely shared `.kiro/specs` layout, so a
repository moves between spec-driven tools without conversion:

```text
.kiro/specs/<feature-name>/
├── .config.kiro      {"specId", "workflowType": "requirements-first", "specType": "feature"}
├── requirements.md   user stories + EARS acceptance criteria
├── design.md         architecture, interfaces, data models, correctness properties
└── tasks.md          checkbox implementation plan
```

Steering documents in `.kiro/steering/` are read before every phase.

## The workflow

1. **Requirements.** `/spec new <feature>` creates the spec folder and the
   agent writes `requirements.md`: an introduction, a glossary, and numbered
   requirements, each a user story with acceptance criteria in EARS form
   (`WHEN …, THE <System> SHALL …`, `IF … THEN …`, `WHILE …`, `WHERE …`).
2. **Design.** When the requirements look right, approve them and the agent
   writes `design.md`: overview, architecture, components and interfaces,
   data models, correctness properties (each tagged with the acceptance
   criteria it validates), error handling and testing strategy.
3. **Tasks.** Approve the design and the agent writes `tasks.md`: an
   implementation plan of numbered checkbox tasks (`1`, `2`, `2.1` …), each
   referencing the acceptance criteria it satisfies (`_Requirements: 1.1, 2.3_`).
   Optional tasks — usually extra tests — are marked `- [ ]*`.
4. **Implementation.** Start one task at a time, or run them all. The agent
   marks a task `[-]` when it starts, implements it, verifies it against the
   referenced requirements, then marks it `[x]`. A single task never runs into
   the next one, so you can review between tasks.

The phase is read from which documents exist; documents appear one
at a time, and approving a phase is what produces the next one. Ask for
changes at any phase — if an earlier document changes after later ones exist,
the agent tells you what is affected before touching them.

Drafting phases run in Plan mode (read-only except the spec folder); task
execution runs in Accept Edits mode.

## Commands

```text
/spec new <feature>                       start with requirements (guided)
/spec quick <feature>                     draft all three documents, then stop
/spec auto <feature>                      write the whole spec and implement it, no approval stops
/spec approve <name> requirements|design|tasks
/spec refine <name> <stage> <feedback>    request changes to a document
/spec task <name> [id]                    start one task (default: the next unfinished one)
/spec run <name> [--optional]             run all remaining tasks (optional ones only with --optional)
/spec list
/spec status <name>                       documents + every task's checkbox
```

`/spec implement <name>` still works as the old spelling of `/spec run`.

## Desktop: the Specs page

Open **Specs** in the sidebar (or the command palette) to drive the whole
workflow without typing commands:

- **New spec** — describe the feature and pick **Guided** (phase by phase,
  approving each document), **Quick** (all three documents at once) or
  **Autopilot** (spec and implementation in one go).
- Each spec shows its progress as four steps — Requirements, Design, Tasks,
  Build. Click a step to read its document, with **Approve**, **Request
  changes** and **Open file** beside it.
- While the agent works on something you sent, the spec shows it as in
  progress and holds its buttons, so a second click can't open a duplicate
  chat.
- A **Next step** bar always offers the one action that moves the spec forward:
  approve the newest document, or start the next task.
- The task list shows each task's state, its requirement references and a
  **Start task** button; **Run all tasks** runs the rest in order.

Everything happens on the Specs page itself — no chat is opened and spec work
never appears in your session list. Each action starts a background agent in
the project; the spec shows what it is doing live (with a **Stop** button) and,
when it finishes, its reply — usually the question for your review. One spec
runs one agent at a time. The page re-reads the files as they change and moves
to a new document as soon as it is written.

The `/spec` command still works in any chat if you prefer to drive specs from
the conversation.

## Older specs

Specs created by earlier JettsTUI versions under `.jettstui/specs/` (with
`status:` frontmatter in each file) keep working with every command and on the
Specs page. New specs are always created under `.kiro/specs/`.

## Work modes

```text
/mode default
/mode plan
/mode accept-edits
```

Press `Shift+Tab` in either the classic CLI or Ink TUI to cycle:

```text
Default → Accept Edits → Plan → Default
```

When slash-command completion is open, `Shift+Tab` keeps its conventional
reverse-completion behavior. A mode changed during a running turn applies to
the next turn.

- `default` uses normal tool behavior.
- `plan` is enforced read-only. The agent can research and may write only below
  `.jettstui/plans/`, `.jettstui/specs/` and `.kiro/specs/`.
- `accept-edits` authorizes workspace edits for the requested work without an
  extra confirmation before every file. Dangerous terminal commands and
  external actions retain their existing approval gates.

Modes are session-scoped. Their instructions are attached to new user turns,
not the system prompt, so switching modes preserves the conversation's cached
prompt prefix.
