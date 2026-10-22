# Compact Desktop UI Redesign Plan

## Objective

Make the JettsTUI **Electron Desktop** interface feel more compact and focused, taking broad interaction cues from Claude's chat UI: a restrained conversation-first workspace, quieter navigation chrome, and less wasted space. Preserve JettsTUI's existing destinations, tabs, controls, and behavior. This is a design and implementation plan; it does not change the UI.

## What the current UI is based on

- This plan targets `apps/desktop`, the native Electron + React chat app. It is separate from the web dashboard, which embeds the Ink TUI, and from `ui-tui` itself.
- The desktop visual contract is in `apps/desktop/DESIGN.md`: flat surfaces, token-based colors, compact shared controls, one primary chat surface, contextual panes, and overlays for short tasks. Its default Prism theme uses ink neutrals with a violet accent, Inter Variable for UI text, and JetBrains Mono for code.
- The shell is contribution-composed (`apps/desktop/src/app/contrib`). The renderer owns presentation/navigation; the gateway owns sessions and agent work.
- The main layout is a customizable pane tree. It can show the session/project sidebar, workspace/chat, and contextual right-side panes. Pane groups have draggable tabs; the layout can be flipped, resized, edited, and persisted.
- The sidebar includes a new-session action; Capabilities; Messaging; Artifacts; Orchestrator; Specs; profile controls; projects/worktrees; pinned and recent sessions; agent, cron, and messaging session groups; and contributed navigation entries.
- Chat is the home surface. The composer, streaming transcript, model controls, tool activity, approvals, and session switching remain first-class.
- Durable pages include Capabilities, Messaging, Artifacts, Orchestrator, Specs, and contributed plugin pages. Settings, Command Center, Cron, Profiles, Agents, Starmap, and Webhooks are route overlays. The sidebar is not the only entry point: keybinds, command palette, and titlebar controls also navigate to these surfaces.

## Existing tabs and tab-like navigation to preserve

1. **Workspace pane tabs:** chat/session panes and opened page panes (including contributed pages) can share a pane group. Preserve tab activation, close behavior, drag-to-rearrange/split/link, the new-session `+`, and the fact that hidden stateful panes stay alive.
2. **Preview tabs:** files/artifacts opened in the chat preview rail have their own tab strip and close/active state.
3. **Capabilities tabs:** Skills, Toolsets, MCP, and Hub (`/skills?tab=...`).
4. **Artifacts filters:** All, Images, Files, and Links (`/artifacts?tab=...`).
5. **Settings navigation and sub-tabs:** config categories (Model, Chat, Appearance, Workspace, Safety, Memory, Voice, Discord, Advanced), Providers (Accounts/API keys), Keys (Tools and other key views), Gateway, Keybinds, Notifications, Plugins, Sessions, and About. Keep deep links/query parameters working.
6. **Contextual pane tabs:** right-side preview/file, review, terminal, and other panes controlled by the pane layout. Preserve their layout persistence and keyboard behavior.

## Redesign direction

- Borrow Claude's broad feel: a calm, conversation-led canvas with a tidy left rail, compact navigation, generous readable message width, and a low-profile composer.
- Reduce visual bulk through tighter vertical rhythm, shorter headers, compact rows, and fewer always-visible labels/actions. Use progressive disclosure for secondary actions and long lists.
- Keep the current Prism theme, accessible contrast, established icon set, design tokens, and flat-surface rules. A compact redesign should come from spacing and hierarchy, not shrinking text until it is hard to read.
- Give the transcript and composer more usable room at common desktop sizes. Keep sidebars and contextual panes resizable, hideable, and reversible.
- Keep tabs discoverable and visually distinct. At narrow widths, allow horizontal scrolling and/or the existing overflow affordance; never silently drop a tab or route.
- Maintain full keyboard access, focus visibility, tooltips where icons need explanation, responsive behavior, and current localization.

## Implementation sequence

1. **Baseline inventory:** capture the current default layout and representative states: empty chat, long transcript, active tool call, many sessions/projects, settings overlay, a page with subtabs, and multiple open workspace/preview tabs. Record current hit targets and layout behavior.
2. **Define compact tokens:** review `apps/desktop/src/app/layout-constants.ts`, shared sidebar/pane primitives, and `apps/desktop/src/styles.css`. Specify a compact spacing/density scale using existing tokens/primitives where possible. Keep normal readable typography and minimum usable hit targets.
3. **Tighten shell chrome:** update the sidebar, titlebar, status area, pane headers/tab strip, and session/project rows in their shared components. Reduce repeated padding and decoration; preserve current actions and contribution slots.
4. **Refine chat canvas:** tune transcript max width, message spacing, tool activity density, and composer height/spacing. Keep all composer controls, model selection, attachments, voice, approvals, and streaming states available.
5. **Refine pages and overlays:** apply the same compact rhythm to Capabilities, Messaging, Artifacts, Orchestrator, Specs, and overlay pages. Preserve each page's current tabs, filters, deep links, and actions.
6. **Responsive and overflow pass:** check small and large window widths, long tab names, many tabs, narrow sidebars, pane flips, hidden panes, and settings sub-navigation. Ensure no clipping, focus loss, or accidental navigation.
7. **Verify behavior and visual quality:** compare before/after screenshots for the baseline states; confirm tab routes, close/drag/split actions, sidebar toggles, saved layouts, keyboard navigation, and reduced-motion/accessibility behavior. Update all four desktop locales if labels change and update `apps/desktop/DESIGN.md` if shared visual contracts change.

## Acceptance criteria

- The interface is visibly denser and gives the conversation more space at the same window size.
- All existing sidebar destinations, pages, overlays, subtabs, workspace tabs, preview tabs, and pane tabs remain reachable and functional.
- Tab state, route/query deep links, drag/close behavior, pane persistence, and keyboard shortcuts continue to work.
- No unreadable text, undersized controls, clipped content, inaccessible icon-only actions, or hidden focus indicators.
- The result follows `apps/desktop/DESIGN.md` and keeps the TUI/dashboard surfaces unchanged.

## Copyable implementation prompt

```text
Redesign the JettsTUI Electron Desktop UI in `apps/desktop` to feel more compact and focused, using Claude's conversation-first desktop layout as high-level inspiration. First inspect the current implementation and `apps/desktop/AGENTS.md` plus `apps/desktop/DESIGN.md`. Do not assume this is the web dashboard or Ink TUI.

Preserve the existing information architecture and every current destination and tab behavior. This includes the session/project sidebar and its profile, pinned/recent, project/worktree, agent, cron, and messaging groups; the workspace pane tabs for chats and opened pages; the new-session tab action; preview/file tabs; Capabilities tabs (Skills, Toolsets, MCP, Hub); Artifacts filters (All, Images, Files, Links); all Settings categories and provider/key subviews; and contextual preview, review, terminal, and other pane tabs. Preserve route/query deep links, keybinds, tab close/activation/drag/split behavior, pane layout persistence, and stateful panes while hidden. Do not remove or merge product features to make the UI appear simpler.

Make the layout denser through a calmer shell, tighter but readable vertical spacing, compact sidebar rows and pane headers, reduced redundant chrome, and progressive disclosure of secondary actions. Give the transcript and composer more usable room. Keep the JettsTUI Prism theme, existing design tokens and primitives, flat-surface rules, established icon system, localization, accessible contrast, visible keyboard focus, and usable hit targets. Keep navigation and tabs discoverable, including when the window is narrow or many tabs are open. Do not shrink typography to achieve compactness.

Work in small shared components and preserve the desktop architecture: React owns presentation/navigation and the gateway owns agent/session work. Do not rebuild the chat in the browser dashboard or alter `ui-tui`. Before implementation, summarize the current components you will touch. Then implement the redesign, update `apps/desktop/DESIGN.md` if a shared visual contract changes, and update all desktop locales if any user-facing strings change. Validate with the repository's existing desktop UI checks and visual states: empty chat, long transcript, active tools, full sidebar, settings/subtab overlays, multiple workspace tabs, preview tabs, narrow window, hidden/flipped panes, keyboard navigation, and persisted layout. Report changed files, preserved tab surfaces, and verification performed.
```

## Source files reviewed

- `apps/desktop/AGENTS.md` — desktop architecture and interaction invariants
- `apps/desktop/DESIGN.md` — visual and interaction contract
- `apps/desktop/src/app/routes.ts` — routes, page/overlay classification
- `apps/desktop/src/app/chat/sidebar/index.tsx` — primary sidebar destinations and groups
- `apps/desktop/src/app/contrib/panes.tsx` and `surfaces.tsx` — shell panes and routed surfaces
- `apps/desktop/src/components/pane-shell/tree/renderer/tree-group.tsx` — pane tab behavior
- `apps/desktop/src/app/settings/index.tsx`, `skills/index.tsx`, and `artifacts/index.tsx` — in-page tab models
- `apps/desktop/src/store/layout.ts` — persisted sidebar/pane layout state
