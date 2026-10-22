import { useEffect, useRef } from 'react'
import spinners, { type BrailleSpinnerName as SpinnerName } from 'unicode-animations'

import { usePaneVisible } from '@/components/pane-shell/pane-visibility'
import { cn } from '@/lib/utils'

export type { SpinnerName }

interface NormalisedSpinner {
  frames: readonly string[]
  interval: number
}

// Some spinners ship multi-character frames. Pull the first cell so each
// frame fits in one monospace box — matches how the TUI uses them.
const FRAMES_BY_NAME: Record<SpinnerName, NormalisedSpinner> = (() => {
  const out = {} as Record<SpinnerName, NormalisedSpinner>

  for (const name of Object.keys(spinners) as SpinnerName[]) {
    const raw = spinners[name]

    out[name] = {
      frames: raw.frames.map(frame => [...frame][0] ?? '⠀'),
      interval: raw.interval
    }
  }

  return out
})()

interface GlyphSpinnerProps {
  ariaLabel?: string
  className?: string
  spinner?: SpinnerName
}

/**
 * One-char glyph spinner driven by `unicode-animations` (braille, orbit, scan,
 * etc. — pick any `spinner` name). Mirrors the spinner used by the Ink TUI so
 * the desktop and terminal experiences read the same visually. Renders inside
 * an `inline-flex` cell with `leading-none` and `items-center` so it sits
 * vertically centred inside its parent's line-box.
 */
export function GlyphSpinner({ ariaLabel = 'Loading', className, spinner = 'braille' }: GlyphSpinnerProps) {
  const spin = FRAMES_BY_NAME[spinner] ?? FRAMES_BY_NAME.braille!
  const ref = useRef<HTMLSpanElement | null>(null)
  // Pause when this surface is a hidden (kept-alive) tab: N mounted tabs each
  // ticking burn CPU for pixels nobody can see.
  const visible = usePaneVisible()

  // Advance the frame by writing the glyph straight to the DOM node, NOT
  // through React state. A one-char spinner re-rendering on every frame is,
  // with the many instances mounted at once (the composer model-pill + status
  // rows, every live subagent, sidebar rows, thread status), that many React
  // commits per tick for a single character React never needs to reconcile —
  // a large share of the app's "busy" render churn (profiling attributed ~195
  // renders to a single idle spinner). The frames and cadence are unchanged;
  // React only renders this leaf on mount / prop change, never per frame. The
  // JSX child below seeds frame 0 and, because React's own view of the text
  // never changes, React leaves these imperative writes alone on re-render.
  useEffect(() => {
    const node = ref.current

    if (!node || !visible) {
      return
    }

    let frame = 0
    node.textContent = spin.frames[0] ?? ''

    const id = window.setInterval(() => {
      frame = (frame + 1) % spin.frames.length
      node.textContent = spin.frames[frame] ?? ''
    }, spin.interval)

    return () => window.clearInterval(id)
  }, [spin, visible])

  return (
    <span
      aria-label={ariaLabel}
      className={cn('inline-flex items-center justify-center font-mono leading-none tabular-nums', className)}
      ref={ref}
      role="status"
    >
      {spin.frames[0]}
    </span>
  )
}
