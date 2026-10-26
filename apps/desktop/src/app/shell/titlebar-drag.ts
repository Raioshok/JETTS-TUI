import { atom } from 'nanostores'

/** A horizontal extent in window px. `right: null` runs to the band's end. */
export interface Span {
  left: number
  right: number | null
}

/** Live x-extents of the fixed titlebar control clusters, published by TitlebarControls. */
export const $titlebarClusters = atom<readonly Span[]>([])

/**
 * Drag strips = the titlebar band minus every control cluster (padded by `pad`).
 * Electron's no-drag carve-out under fixed/transformed elements is unreliable, so
 * a drag region must never overlap a clickable cluster — measured, not counted,
 * so adding a button can't silently kill its clicks again.
 */
export function titlebarDragGaps(clusters: readonly Span[], pad = 4): Span[] {
  const gaps: Span[] = []
  let x = 0

  for (const cluster of [...clusters].sort((a, b) => a.left - b.left)) {
    const left = Math.max(0, cluster.left - pad)

    if (left > x) {
      gaps.push({ left: x, right: left })
    }

    x = Math.max(x, (cluster.right ?? Infinity) + pad)
  }

  if (Number.isFinite(x)) {
    gaps.push({ left: x, right: null })
  }

  return gaps
}

const sameSpans = (a: readonly Span[], b: readonly Span[]) =>
  a.length === b.length && a.every((span, i) => span.left === b[i].left && span.right === b[i].right)

/** Measure every `[data-titlebar-cluster]` and publish when the extents changed. */
export function publishTitlebarClusters() {
  const spans = [...document.querySelectorAll<HTMLElement>('[data-titlebar-cluster]')].map(el => {
    const rect = el.getBoundingClientRect()

    return { left: Math.floor(rect.left), right: Math.ceil(rect.right) }
  })

  if (!sameSpans($titlebarClusters.get(), spans)) {
    $titlebarClusters.set(spans)
  }
}
