/**
 * Code mode — a layout, not a route: the file tree beside a wide editor, with
 * the chat alongside. Entering it remembers the layout (tree, preset, the
 * user's sash sizes and pinned panes) so leaving restores exactly what was
 * there, even across a restart while still in code mode. Neither direction
 * opens toggle-gated panes (terminal, logs): visibility is left as it was.
 */

import { computed } from 'nanostores'

import { group, isLayoutNode, type LayoutNode, split } from '@/components/pane-shell/tree/model'
import { $activePresetId, $layoutTree, $userPlacedPanes, applyTree } from '@/components/pane-shell/tree/store'
import { registry } from '@/contrib/registry'
import { readJson, writeJson } from '@/lib/storage'

import { setFileBrowserOpen } from './layout'
import { $paneStates, setPaneHeightOverride, setPaneWidthOverride } from './panes'

export const CODE_PRESET_ID = 'code'

const RETURN_KEY = 'jettstui.desktop.codeMode.return.v1'

/**
 * sessions | files | editor | chat (+ review / flow, terminal below) — the same
 * pane set as the default layout, so nothing is left for adoption to guess at.
 * The tree sits LEFT of main, so `dockPaneBeside` keeps the preview on the
 * tree's right: the shape this preset declares, so auto-docking never fights
 * it. Review, flow and the terminal collapse until opened, as everywhere.
 */
export const CODE_TREE: LayoutNode = split(
  'row',
  [
    group(['sessions'], { id: 'grp-sessions' }),
    split(
      'column',
      [
        split(
          'row',
          [
            group(['files'], { id: 'grp-files' }),
            group(['preview'], { id: 'grp-preview' }),
            group(['workspace'], { id: 'grp-main' }),
            group(['review'], { id: 'grp-review' }),
            group(['flow'], { id: 'grp-flow' })
          ],
          [1, 3, 1.6, 1, 1.1],
          'spl-code-work'
        ),
        group(['terminal'], { id: 'grp-terminal' })
      ],
      [3, 1],
      'spl-code-main'
    )
  ],
  [1, 5],
  'spl-code'
)

export const $codeMode = computed($activePresetId, id => id === CODE_PRESET_ID)

interface PaneSizes {
  height?: number
  width?: number
}

interface ReturnPoint {
  presetId: string
  sizes: Record<string, PaneSizes>
  tree: LayoutNode
  userPlaced: string[]
}

/** The editor's track width in code mode: most of the room the chat doesn't need. */
export function codeEditorWidth(viewportWidth: number): number {
  return Math.round(Math.min(Math.max(viewportWidth * 0.44, 480), 1100))
}

function currentSizes(): Record<string, PaneSizes> {
  const sizes: Record<string, PaneSizes> = {}

  for (const [id, state] of Object.entries($paneStates.get())) {
    if (state.widthOverride !== undefined || state.heightOverride !== undefined) {
      sizes[id] = { height: state.heightOverride, width: state.widthOverride }
    }
  }

  return sizes
}

function readReturnPoint(): ReturnPoint | null {
  const saved = readJson<ReturnPoint>(RETURN_KEY)

  return saved && typeof saved.presetId === 'string' && isLayoutNode(saved.tree) && Array.isArray(saved.userPlaced)
    ? saved
    : null
}

function defaultLayout(): { id: string; tree: LayoutNode } | null {
  const preset = registry.getArea('layouts').find(c => c.id === 'default')

  return preset && isLayoutNode(preset.data) ? { id: preset.id, tree: preset.data } : null
}

export function enterCodeMode(viewportWidth = window.innerWidth) {
  const tree = $layoutTree.get()

  // Secondary windows have no layout tree; re-entering is a no-op (and must
  // not overwrite the return point with the code layout itself).
  if (!tree || $codeMode.get()) {
    return
  }

  writeJson(RETURN_KEY, {
    presetId: $activePresetId.get(),
    sizes: currentSizes(),
    tree,
    userPlaced: [...$userPlacedPanes.get()]
  } satisfies ReturnPoint)
  // A mode switch rearranges what's there — it doesn't open the terminal/logs.
  applyTree(structuredClone(CODE_TREE), CODE_PRESET_ID, { revealPanes: false })
  setFileBrowserOpen(true)
  setPaneWidthOverride('preview', codeEditorWidth(viewportWidth))
}

export function exitCodeMode() {
  if (!$layoutTree.get() || !$codeMode.get()) {
    return
  }

  const saved = readReturnPoint()
  const fallback = saved ? null : defaultLayout()

  if (saved) {
    applyTree(structuredClone(saved.tree), saved.presetId, {
      revealPanes: false,
      userPlaced: new Set(saved.userPlaced)
    })

    // applyTree resets every sash size; put the user's back.
    for (const [id, size] of Object.entries(saved.sizes)) {
      setPaneWidthOverride(id, size.width)
      setPaneHeightOverride(id, size.height)
    }
  } else if (fallback) {
    applyTree(structuredClone(fallback.tree), fallback.id, { revealPanes: false })
  }

  writeJson(RETURN_KEY, null)
}
