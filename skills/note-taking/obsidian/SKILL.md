---
name: obsidian
description: Read, search, create, and edit notes in the Obsidian vault.
platforms: [linux, macos, windows]
---

# Obsidian Vault

Use this skill for filesystem-first Obsidian vault work: reading notes, listing notes, searching note files, creating notes, appending content, and adding wikilinks.

## Vault path

Use a known or resolved vault path before calling file tools.

Resolve the path in this order: an explicit path from the user, `obsidian.vault_path`
in `config.yaml`, the legacy `OBSIDIAN_VAULT_PATH` environment variable, then
`~/Documents/FreeIDE Brain`. Behavioral configuration belongs in `config.yaml`;
the environment variable is supported for backward compatibility.

File tools do not expand shell variables. Do not pass paths containing `$OBSIDIAN_VAULT_PATH` to `read_file`, `write_file`, `patch`, or `search_files`; resolve the vault path first and pass a concrete absolute path. Vault paths may contain spaces, which is another reason to prefer file tools over shell commands.

If the vault path is unknown, `terminal` is acceptable for resolving `OBSIDIAN_VAULT_PATH` or checking whether the fallback path exists. Once the path is known, switch back to file tools.

## FreeIDE Brain mode

When `.freeide-brain.json` exists at the vault root, this is a managed project
brain. Read `00-System/Agent Protocol.md`, `01-Projects/Project Index.md`, and
only the selected project's index before retrieving other notes. Follow the
progressive retrieval path: index, smallest useful summary tier, linked maps,
then targeted raw source. Never scan the whole vault during ordinary work.

- `/brain init` creates or safely upgrades the structure without overwriting
  customized notes.
- `/brain capture <text>` is the low-friction inbox path.
- `/brain sync` refreshes only changed project material by source hash.
- `/brain improve` triages and reconciles only when a material-change gate fires.
- `/brain doctor` explicitly audits structure and unresolved links.

Treat summaries as derivative caches. If a source hash changed, the source wins.
Keep contradictory claims with provenance and mark them for review rather than
silently choosing one. Do not claim token savings until baseline and current
usage are measured on comparable tasks.

The official Obsidian CLI is optional and useful for opening notes or querying
native Obsidian state. Filesystem tools remain the portable default.

## Read a note

Use `read_file` with the resolved absolute path to the note. Prefer this over `cat` because it provides line numbers and pagination.

## List notes

Use `search_files` with `target: "files"` and the resolved vault path. Prefer this over `find` or `ls`.

- To list all markdown notes, use `pattern: "*.md"` under the vault path.
- To list a subfolder, search under that subfolder's absolute path.

## Search

Use `search_files` for both filename and content searches. Prefer this over `grep`, `find`, or `ls`.

- For filenames, use `search_files` with `target: "files"` and a filename `pattern`.
- For note contents, use `search_files` with `target: "content"`, the content regex as `pattern`, and `file_glob: "*.md"` when you want to restrict matches to markdown notes.

## Create a note

Use `write_file` with the resolved absolute path and the full markdown content. Prefer this over shell heredocs or `echo` because it avoids shell quoting issues and returns structured results.

## Append to a note

Prefer a native file-tool workflow when it is not awkward:

- Read the target note with `read_file`.
- Use `patch` for an anchored append when there is stable context, such as adding a section after an existing heading or appending before a known trailing block.
- Use `write_file` when rewriting the whole note is clearer than constructing a fragile patch.

For an anchored append with `patch`, replace the anchor with the anchor plus the new content.

For a simple append with no stable context, `terminal` is acceptable if it is the clearest safe option.

## Targeted edits

Use `patch` for focused note changes when the current content gives you stable context. Prefer this over shell text rewriting.

## Wikilinks

Obsidian links notes with `[[Note Name]]` syntax. When creating notes, use these to link related content.
