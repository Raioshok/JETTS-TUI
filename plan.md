# Compact Desktop UI Redesign Plan

## Objective

Make the JettsTUI **Electron Desktop** interface feel like the attached reference's compact, organized desktop workspace while remaining unmistakably JettsTUI. Borrow its layout rhythm, compact navigation, clean tabbed workspace, and clear content hierarchy. Keep JettsTUI's own Prism persona, colors, features, navigation labels, tabs, Orchestrator, controls, and behavior. This is a design and implementation plan; it does not change the UI.

## What the current UI is based on

- This plan targets `apps/desktop`, the native Electron + React chat app. It is separate from the web dashboard, which embeds the Ink TUI, and from `ui-tui` itself.
- The desktop visual contract is in `apps/desktop/DESIGN.md`: flat surfaces, token-based colors, compact shared controls, one primary chat surface, contextual panes, and overlays for short tasks. Its default Prism theme uses ink neutrals with a violet accent, Inter Variable for UI text, and JetBrains Mono for code.
- The shell is contribution-composed (`apps/desktop/src/app/contrib`). The renderer owns presentation/navigation; the gateway owns sessions and agent work.
- The main layout is a customizable pane tree. It can show the session/project sidebar, workspace/chat, and contextual right-side panes. Pane groups have draggable tabs; the layout can be flipped, resized, edited, and persisted.
- The sidebar includes a new-session action; Capabilities; Messaging; Artifacts; Orchestrator; Specs; profile controls; projects/worktrees; pinned and recent sessions; agent, cron, and messaging session groups; and contributed navigation entries.
- Chat is the home surface. The composer, streaming transcript, model controls, tool activity, approvals, and session switching remain first-class.
- Durable pages include Capabilities, Messaging, Artifacts, Orchestrator, Specs, and contributed plugin pages. Settings, Command Center, Cron, Profiles, Agents, Starmap, and Webhooks are route overlays. The sidebar is not the only entry point: keybinds, command palette, and titlebar controls also navigate to these surfaces.
- The reference is inspiration for layout and density only. Do not copy its brand, palette, labels, or product modes. Keep JettsTUI names and identity, including Orchestrator, and retain all current destinations in their appropriate navigation or contextual workspace locations.

## Existing tabs and tab-like navigation to preserve

1. **Workspace pane tabs:** chat/session panes and opened page panes (including contributed pages) can share a pane group. Preserve tab activation, close behavior, drag-to-rearrange/split/link, the new-session `+`, and the fact that hidden stateful panes stay alive.
2. **Preview tabs:** files/artifacts opened in the chat preview rail have their own tab strip and close/active state.
3. **Capabilities tabs:** Skills, Toolsets, MCP, and Hub (`/skills?tab=...`).
4. **Artifacts filters:** All, Images, Files, and Links (`/artifacts?tab=...`).
5. **Settings navigation and sub-tabs:** config categories (Model, Chat, Appearance, Workspace, Safety, Memory, Voice, Discord, Advanced), Providers (Accounts/API keys), Keys (Tools and other key views), Gateway, Keybinds, Notifications, Plugins, Sessions, and About. Keep deep links/query parameters working.
6. **Contextual pane tabs:** right-side preview/file, review, terminal, and other panes controlled by the pane layout. Preserve their layout persistence and keyboard behavior.

## Redesign direction from the reference image

- Use the reference's overall composition: a clearly bounded left navigation rail, compact top chrome, tidy tabbed work area, and a broad focused content canvas. Keep JettsTUI's Prism identity, current theme colors/accent, typography, icon vocabulary, and light/dark behavior; do not copy the screenshot's gold accent or impose a new palette.
- Keep a persistent left rail with compact icon-and-label navigation, clear grouping, recents/session rows, and a bottom-pinned profile/account area where it fits the current shell. Preserve JettsTUI's profile, session, project/worktree, agent, cron, messaging, Orchestrator, Specs, Capabilities, Artifacts, and contributed navigation. Group/scroll long lists instead of removing destinations.
- Keep the existing JettsTUI navigation and tab vocabulary. Do not add Chats / Colab / Code mode tabs from the reference. Use existing titlebar and workspace chrome with compact proportions; keep all existing pages and overlays reachable.
- In workspaces that show files or code, use a compact workspace header: contextual navigation, horizontal closeable existing tabs, and existing actions/indicators where available. A breadcrumb row and broad low-chrome content area are visual cues to apply where they fit; reuse current preview/file and pane systems rather than inventing an editor.
- Keep chat calm and central: readable transcript, restrained tool/status details, and a compact composer anchored to the bottom. Reclaim space with tighter row/header spacing and progressive disclosure, not by shrinking type or targets.
- Keep all current session/page/preview/pane tabs and in-page filters/subtabs discoverable and operable. Allow horizontal tab scrolling/overflow affordances at narrow widths; preserve tab activation, close, drag/split/link, route deep links, and persistence.
- Use existing primitives, tokens, icon set, i18n, focus behavior, and flat-surface contract. Preserve responsive layout, keyboard navigation, accessible contrast, and dark mode.

## Implementation sequence

1. **Baseline and map:** capture current UI states and map the reference's layout cues (rail, compact chrome, tabbed workspace, content canvas) onto JettsTUI's existing surfaces. Preserve every current destination and its label.
2. **Shell frame:** refine the left navigation rail, recents, pinned account/profile footer, and window/titlebar chrome to match the screenshot's compact proportions while retaining JettsTUI's current identity and navigation.
3. **Workspace chrome:** refine contextual workspace header, existing pane/file tabs, breadcrumbs where useful, existing actions/indicators, and content canvas. Reuse existing file preview and pane systems.
4. **Chat canvas:** tighten transcript rhythm, tool/status details, and composer. Keep controls, streaming states, approvals, voice, model selection, and attachments available.
5. **Pages, overlays, and tabs:** carry the compact style through Capabilities, Messaging, Artifacts, Orchestrator, Specs, and overlays. Preserve all tab sets, filters, deep links, and existing actions.
6. **Responsive and overflow pass:** check window sizes, long/many tabs, narrow sidebars, pane flips, hidden panes, keyboard focus, and settings sub-navigation.
7. **Verify:** compare reference and before/after screenshots at representative states; confirm navigation, tab close/drag/split, pane persistence, keybinds, accessibility, dark mode, and localization. Update `apps/desktop/DESIGN.md` when shared contracts change.

## Acceptance criteria

- The interface is visibly denser and gives the conversation more space at the same window size.
- All existing sidebar destinations, pages, overlays, subtabs, workspace tabs, preview tabs, and pane tabs remain reachable and functional.
- Tab state, route/query deep links, drag/close behavior, pane persistence, and keyboard shortcuts continue to work.
- No unreadable text, undersized controls, clipped content, inaccessible icon-only actions, or hidden focus indicators.
- The result follows `apps/desktop/DESIGN.md` and keeps the TUI/dashboard surfaces unchanged.

## Copyable implementation prompt

```text
Redesign the JettsTUI Electron Desktop UI in `apps/desktop` so it feels like the attached reference image: compact, organized, and centered on a clean tabbed workspace. Treat the image as inspiration for layout, spacing, and hierarchy only. Keep JettsTUI unmistakable: retain the existing Prism persona, theme colors and accents, typography, product naming, navigation destinations, Orchestrator, features, and tabs. Do not copy the reference brand, palette, or product labels/modes. First inspect the current implementation and `apps/desktop/AGENTS.md` plus `apps/desktop/DESIGN.md`. Do not assume this is the web dashboard or Ink TUI.

Preserve the existing information architecture and every current destination and tab behavior. This includes the session/project sidebar and its profile, pinned/recent, project/worktree, agent, cron, and messaging groups; the workspace pane tabs for chats and opened pages; the new-session tab action; preview/file tabs; Capabilities tabs (Skills, Toolsets, MCP, Hub); Artifacts filters (All, Images, Files, Links); all Settings categories and provider/key subviews; and contextual preview, review, terminal, and other pane tabs. Preserve route/query deep links, keybinds, tab close/activation/drag/split behavior, pane layout persistence, and stateful panes while hidden. Do not remove or merge product features to make the UI appear simpler.

Make the layout denser with tighter readable spacing, compact sidebar rows and pane headers, minimal decoration, and progressive disclosure. Preserve the current navigation labels and surfaces, especially Orchestrator, along with all chat/session/page/preview/pane tabs and in-page filters/subtabs. In code/file workspaces, reuse the current file tree, preview, tabs, and panes; apply breadcrumbs and a broad content canvas only where they suit existing functionality. Give chat more usable room. Keep JettsTUI's existing Prism design tokens, palette and accents, both theme modes, primitives and icon system, localization, accessible contrast, visible keyboard focus, and usable hit targets. Keep every current route, overlay, and tab discoverable, including at narrow widths or with many tabs. Do not shrink typography to achieve compactness.

Work in small shared components and preserve desktop architecture: React owns presentation/navigation and the gateway owns agent/session work. Do not rebuild chat in the browser dashboard or alter `ui-tui`. Before implementation, map the reference's layout cues to existing JettsTUI components and list the components to change. Then implement the redesign, update `apps/desktop/DESIGN.md` if a shared visual contract changes, and update all desktop locales if strings change. Validate empty chat, long transcript, active tools, full sidebar, Orchestrator, settings/subtab overlays, multiple workspace tabs, preview tabs, file workspace, narrow window, hidden/flipped panes, keyboard navigation, and persisted layout. Report changed files, preserved JettsTUI identity and tab surfaces, and verification performed.
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
