---
sidebar_position: 5
title: "Bundled Skills Catalog"
description: "Catalog of bundled skills that ship with JettsTUI"
---

# Bundled Skills Catalog

JettsTUI ships with a built-in skill library copied into `~/.jettstui/skills/` on a new install. Each skill below links to a Markdown guide with its definition, setup, and usage.

JettsTUI syncs bundled skills on `jetts-tui update`, while respecting local deletions and user edits. If a listed skill is missing from your profile's skills directory, restore it with `jetts-tui skills reset <name> --restore`.

This catalog is a checked-in snapshot. Use the repository's `skills/` and `optional-skills/` directories as the source of truth when it differs.

## apple

| Skill | Description | Path |
|-------|-------------|------|
| [`apple-notes`](../user-guide/skills/bundled/apple/apple-apple-notes.md) | Manage Apple Notes via memo CLI: create, search, edit. | `apple/apple-notes` |
| [`apple-reminders`](../user-guide/skills/bundled/apple/apple-apple-reminders.md) | Apple Reminders via remindctl: add, list, complete. | `apple/apple-reminders` |
| [`findmy`](../user-guide/skills/bundled/apple/apple-findmy.md) | Track Apple devices/AirTags via FindMy.app on macOS. | `apple/findmy` |
| [`imessage`](../user-guide/skills/bundled/apple/apple-imessage.md) | Send and receive iMessages/SMS via the imsg CLI on macOS. | `apple/imessage` |

## autonomous-ai-agents

| Skill | Description | Path |
|-------|-------------|------|
| [`claude-code`](../user-guide/skills/bundled/autonomous-ai-agents/autonomous-ai-agents-claude-code.md) | Delegate coding to Claude Code CLI (features, PRs). | `autonomous-ai-agents/claude-code` |
| [`codex`](../user-guide/skills/bundled/autonomous-ai-agents/autonomous-ai-agents-codex.md) | Delegate coding to OpenAI Codex CLI (features, PRs). | `autonomous-ai-agents/codex` |
| [`computer-use`](../user-guide/skills/bundled/autonomous-ai-agents/autonomous-ai-agents-computer-use.md) | Drive the user's desktop in the background — clicking, typing, scrolling, dragging — without stealing the cursor, keyboard focus, or switching virtual desktops / Spaces. Cross-platform: macOS, Windows, Linux. Works with any tool-capable... | `autonomous-ai-agents/computer-use` |
| [`jettstui`](../user-guide/skills/bundled/autonomous-ai-agents/autonomous-ai-agents-jettstui.md) | Use, configure, theme, extend, and orchestrate JettsTUI. | `autonomous-ai-agents/jettstui` |
| [`opencode`](../user-guide/skills/bundled/autonomous-ai-agents/autonomous-ai-agents-opencode.md) | Delegate coding to OpenCode CLI (features, PR review). | `autonomous-ai-agents/opencode` |
| [`token-efficient-work`](../user-guide/skills/bundled/autonomous-ai-agents/autonomous-ai-agents-token-efficient-work.md) | Plan and execute expensive or repeated agent work with explicit budgets, narrow delegation, concise reporting, persistent preferences, and resumable progress. | `autonomous-ai-agents/token-efficient-work` |

## creative

| Skill | Description | Path |
|-------|-------------|------|
| [`architecture-diagram`](../user-guide/skills/bundled/creative/creative-architecture-diagram.md) | Dark-themed SVG architecture/cloud/infra diagrams as HTML. | `creative/architecture-diagram` |
| [`ascii-art`](../user-guide/skills/bundled/creative/creative-ascii-art.md) | ASCII art: pyfiglet, cowsay, boxes, image-to-ascii. | `creative/ascii-art` |
| [`ascii-video`](../user-guide/skills/bundled/creative/creative-ascii-video.md) | ASCII video: convert video/audio to colored ASCII MP4/GIF. | `creative/ascii-video` |
| [`baoyu-infographic`](../user-guide/skills/bundled/creative/creative-baoyu-infographic.md) | Infographics: 21 layouts x 21 styles (信息图, 可视化). | `creative/baoyu-infographic` |
| [`claude-design`](../user-guide/skills/bundled/creative/creative-claude-design.md) | Design one-off HTML artifacts (landing, deck, prototype). | `creative/claude-design` |
| [`comfyui`](../user-guide/skills/bundled/creative/creative-comfyui.md) | Generate images, video, and audio via diffusion workflows. | `creative/comfyui` |
| [`design-md`](../user-guide/skills/bundled/creative/creative-design-md.md) | Author/validate/export Google's DESIGN.md token spec files. | `creative/design-md` |
| [`excalidraw`](../user-guide/skills/bundled/creative/creative-excalidraw.md) | Hand-drawn Excalidraw JSON diagrams (arch, flow, seq). | `creative/excalidraw` |
| [`humanizer`](../user-guide/skills/bundled/creative/creative-humanizer.md) | Humanize text: strip AI-isms and add real voice. | `creative/humanizer` |
| [`manim-video`](../user-guide/skills/bundled/creative/creative-manim-video.md) | Manim CE animations: 3Blue1Brown math/algo videos. | `creative/manim-video` |
| [`p5js`](../user-guide/skills/bundled/creative/creative-p5js.md) | p5.js sketches: gen art, shaders, interactive, 3D. | `creative/p5js` |
| [`popular-web-designs`](../user-guide/skills/bundled/creative/creative-popular-web-designs.md) | 54 real design systems (Stripe, Linear, Vercel) as HTML/CSS. | `creative/popular-web-designs` |
| [`pretext`](../user-guide/skills/bundled/creative/creative-pretext.md) | Build creative browser demos with DOM-free text layout. | `creative/pretext` |
| [`sketch`](../user-guide/skills/bundled/creative/creative-sketch.md) | Throwaway HTML mockups: 2-3 design variants to compare. | `creative/sketch` |
| [`songwriting-and-ai-music`](../user-guide/skills/bundled/creative/creative-songwriting-and-ai-music.md) | Songwriting craft and Suno AI music prompts. | `creative/songwriting-and-ai-music` |
| [`touchdesigner-mcp`](../user-guide/skills/bundled/creative/creative-touchdesigner-mcp.md) | Control TouchDesigner via twozero MCP. | `creative/touchdesigner-mcp` |

## email

| Skill | Description | Path |
|-------|-------------|------|
| [`himalaya`](../user-guide/skills/bundled/email/email-himalaya.md) | Himalaya CLI: IMAP/SMTP email from terminal. | `email/himalaya` |

## github

| Skill | Description | Path |
|-------|-------------|------|
| [`codebase-inspection`](../user-guide/skills/bundled/github/github-codebase-inspection.md) | Inspect codebases w/ pygount: LOC, languages, ratios. | `github/codebase-inspection` |
| [`github-auth`](../user-guide/skills/bundled/github/github-github-auth.md) | GitHub auth setup: HTTPS tokens, SSH keys, gh CLI login. | `github/github-auth` |
| [`github-code-review`](../user-guide/skills/bundled/github/github-github-code-review.md) | Review PRs: diffs, inline comments via gh or REST. | `github/github-code-review` |
| [`github-issues`](../user-guide/skills/bundled/github/github-github-issues.md) | Create, triage, label, assign GitHub issues via gh or REST. | `github/github-issues` |
| [`github-pr-workflow`](../user-guide/skills/bundled/github/github-github-pr-workflow.md) | GitHub PR lifecycle: branch, commit, open, CI, merge. | `github/github-pr-workflow` |
| [`github-repo-management`](../user-guide/skills/bundled/github/github-github-repo-management.md) | Clone/create/fork repos; manage remotes, releases. | `github/github-repo-management` |

## media

| Skill | Description | Path |
|-------|-------------|------|
| [`gif-search`](../user-guide/skills/bundled/media/media-gif-search.md) | Search/download GIFs from Tenor via curl + jq. | `media/gif-search` |
| [`songsee`](../user-guide/skills/bundled/media/media-songsee.md) | Audio spectrograms/features (mel, chroma, MFCC) via CLI. | `media/songsee` |
| [`youtube-content`](../user-guide/skills/bundled/media/media-youtube-content.md) | YouTube transcripts to summaries, threads, blogs. | `media/youtube-content` |

## mlops

| Skill | Description | Path |
|-------|-------------|------|
| [`evaluating-llms-harness`](../user-guide/skills/bundled/mlops/mlops-evaluation-evaluating-llms-harness.md) | lm-eval-harness: benchmark LLMs (MMLU, GSM8K, etc.). | `mlops/evaluation/evaluating-llms-harness` |
| [`huggingface-hub`](../user-guide/skills/bundled/mlops/mlops-huggingface-hub.md) | HuggingFace hf CLI: search/download/upload models, datasets. | `mlops/huggingface-hub` |
| [`llama-cpp`](../user-guide/skills/bundled/mlops/mlops-inference-llama-cpp.md) | llama.cpp local GGUF inference + HF Hub model discovery. | `mlops/inference/llama-cpp` |
| [`serving-llms-vllm`](../user-guide/skills/bundled/mlops/mlops-inference-serving-llms-vllm.md) | vLLM: high-throughput LLM serving, OpenAI API, quantization. | `mlops/inference/serving-llms-vllm` |
| [`weights-and-biases`](../user-guide/skills/bundled/mlops/mlops-evaluation-weights-and-biases.md) | W&B: log ML experiments, sweeps, model registry, dashboards. | `mlops/evaluation/weights-and-biases` |

## note-taking

| Skill | Description | Path |
|-------|-------------|------|
| [`obsidian`](../user-guide/skills/bundled/note-taking/note-taking-obsidian.md) | Read, search, create, and edit notes in the Obsidian vault. | `note-taking/obsidian` |

## productivity

| Skill | Description | Path |
|-------|-------------|------|
| [`airtable`](../user-guide/skills/bundled/productivity/productivity-airtable.md) | Airtable REST API via curl. Records CRUD, filters, upserts. | `productivity/airtable` |
| [`docx`](../user-guide/skills/bundled/productivity/productivity-docx.md) | Create, read, edit Word .docx documents and templates. | `productivity/docx` |
| [`google-workspace`](../user-guide/skills/bundled/productivity/productivity-google-workspace.md) | Gmail, Calendar, Drive, Docs, Sheets via gws CLI or Python. | `productivity/google-workspace` |
| [`maps`](../user-guide/skills/bundled/productivity/productivity-maps.md) | Geocode, POIs, routes, timezones via OpenStreetMap/OSRM. | `productivity/maps` |
| [`nano-pdf`](../user-guide/skills/bundled/productivity/productivity-nano-pdf.md) | Edit text in existing PDFs via natural-language prompts. | `productivity/nano-pdf` |
| [`notion`](../user-guide/skills/bundled/productivity/productivity-notion.md) | Notion API + ntn CLI: pages, databases, markdown, Workers. | `productivity/notion` |
| [`ocr-and-documents`](../user-guide/skills/bundled/productivity/productivity-ocr-and-documents.md) | Extract text from PDFs/scans (pymupdf, marker-pdf). | `productivity/ocr-and-documents` |
| [`pdf`](../user-guide/skills/bundled/productivity/productivity-pdf.md) | Create, merge, split, fill, and secure PDF files. | `productivity/pdf` |
| [`powerpoint`](../user-guide/skills/bundled/productivity/productivity-powerpoint.md) | Create, read, edit .pptx decks, slides, notes, templates. | `productivity/powerpoint` |
| [`teams-meeting-pipeline`](../user-guide/skills/bundled/productivity/productivity-teams-meeting-pipeline.md) | Teams meeting summaries, job replay, Graph subscriptions. | `productivity/teams-meeting-pipeline` |
| [`xlsx`](../user-guide/skills/bundled/productivity/productivity-xlsx.md) | Create, read, edit Excel .xlsx spreadsheets and CSVs. | `productivity/xlsx` |

## research

| Skill | Description | Path |
|-------|-------------|------|
| [`arxiv`](../user-guide/skills/bundled/research/research-arxiv.md) | Search arXiv papers by keyword, author, category, or ID. | `research/arxiv` |
| [`blogwatcher`](../user-guide/skills/bundled/research/research-blogwatcher.md) | Monitor blogs and RSS/Atom feeds via blogwatcher-cli tool. | `research/blogwatcher` |
| [`llm-wiki`](../user-guide/skills/bundled/research/research-llm-wiki.md) | Karpathy's LLM Wiki: build/query interlinked markdown KB. | `research/llm-wiki` |
| [`polymarket`](../user-guide/skills/bundled/research/research-polymarket.md) | Query Polymarket: markets, prices, orderbooks, history. | `research/polymarket` |
| [`research-paper-writing`](../user-guide/skills/bundled/research/research-research-paper-writing.md) | Write ML papers for NeurIPS/ICML/ICLR: design→submit. | `research/research-paper-writing` |

## smart-home

| Skill | Description | Path |
|-------|-------------|------|
| [`openhue`](../user-guide/skills/bundled/smart-home/smart-home-openhue.md) | Control Philips Hue lights, scenes, rooms via OpenHue CLI. | `smart-home/openhue` |

## social-media

| Skill | Description | Path |
|-------|-------------|------|
| [`xurl`](../user-guide/skills/bundled/social-media/social-media-xurl.md) | X/Twitter via xurl CLI: raw post search, posting, DM, media. | `social-media/xurl` |

## software-development

| Skill | Description | Path |
|-------|-------------|------|
| [`dogfood`](../user-guide/skills/bundled/software-development/software-development-dogfood.md) | Exploratory QA of web apps: find bugs, evidence, reports. | `software-development/dogfood` |
| [`jettstui-skill-authoring`](../user-guide/skills/bundled/software-development/software-development-jettstui-skill-authoring.md) | Author in-repo SKILL.md files: frontmatter and structure. | `software-development/jettstui-skill-authoring` |
| [`inspecting-jettstui-desktop-dom`](../user-guide/skills/bundled/software-development/software-development-inspecting-jettstui-desktop-dom.md) | Read the live JettsTUI desktop DOM/CSS over CDP. | `software-development/inspecting-jettstui-desktop-dom` |
| [`node-inspect-debugger`](../user-guide/skills/bundled/software-development/software-development-node-inspect-debugger.md) | Debug Node.js via --inspect + Chrome DevTools Protocol CLI. | `software-development/node-inspect-debugger` |
| [`plan`](../user-guide/skills/bundled/software-development/software-development-plan.md) | Write a markdown plan to .jettstui/plans/; no execution. | `software-development/plan` |
| [`python-debugpy`](../user-guide/skills/bundled/software-development/software-development-python-debugpy.md) | Debug Python: pdb REPL + debugpy remote (DAP). | `software-development/python-debugpy` |
| [`requesting-code-review`](../user-guide/skills/bundled/software-development/software-development-requesting-code-review.md) | Pre-commit review: security scan, quality gates, auto-fix. | `software-development/requesting-code-review` |
| [`simplify-code`](../user-guide/skills/bundled/software-development/software-development-simplify-code.md) | Parallel 4-agent cleanup of recent code changes. | `software-development/simplify-code` |
| [`spike`](../user-guide/skills/bundled/software-development/software-development-spike.md) | Throwaway experiments to validate an idea before build. | `software-development/spike` |
| [`systematic-debugging`](../user-guide/skills/bundled/software-development/software-development-systematic-debugging.md) | 4-phase root cause debugging: understand bugs before fixing. | `software-development/systematic-debugging` |
| [`test-driven-development`](../user-guide/skills/bundled/software-development/software-development-test-driven-development.md) | TDD: enforce RED-GREEN-REFACTOR, tests before code. | `software-development/test-driven-development` |
