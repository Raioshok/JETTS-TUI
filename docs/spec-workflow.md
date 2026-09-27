# Spec-driven development

FreeIDE's interactive CLI supports a Kiro-style, three-document specification
workflow. Specs live inside the active workspace at:

```text
.freeide/specs/<feature>/
├── requirements.md
├── design.md
└── tasks.md
```

No hidden fourth state file is created. Each document carries `draft` or
`approved` status in its YAML frontmatter.

## Workflow

```text
/spec new offline search
/spec approve offline-search requirements
/spec approve offline-search design
/spec approve offline-search tasks
/spec implement offline-search
```

`/spec new` enters Plan mode and asks the agent to refine requirements after
inspecting the repository. Approval is sequential: design cannot be approved
before requirements, and tasks cannot be approved before design. Implementation
requires an approved task list and switches to Accept Edits mode.

Use `/spec quick <feature>` when you want the agent to draft all three files in
one pass. New specs use Kiro-compatible `tasks.md`; existing `tasklist.md`
specs continue to work without migration.

Inspect progress at any point:

```text
/spec list
/spec status offline-search
```

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
  `.freeide/plans/` and `.freeide/specs/`.
- `accept-edits` authorizes workspace edits for the requested work without an
  extra confirmation before every file. Dangerous terminal commands and
  external actions retain their existing approval gates.

Modes are session-scoped. Their instructions are attached to new user turns,
not the system prompt, so switching modes preserves the conversation's cached
prompt prefix.
