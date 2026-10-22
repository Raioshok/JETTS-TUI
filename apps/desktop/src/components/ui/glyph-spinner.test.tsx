import { act, render } from '@testing-library/react'
import { Profiler, type ProfilerOnRenderCallback } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { PaneVisibleContext } from '@/components/pane-shell/pane-visibility'
import { GlyphSpinner } from '@/components/ui/glyph-spinner'

describe('GlyphSpinner', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('animates through frames via the DOM without re-rendering per frame', () => {
    vi.useFakeTimers()

    let commits = 0

    const onRender: ProfilerOnRenderCallback = () => {
      commits += 1
    }

    const { container } = render(
      <Profiler id="glyph" onRender={onRender}>
        <GlyphSpinner spinner="braille" />
      </Profiler>
    )

    const span = container.querySelector('[role="status"]') as HTMLElement
    const commitsAfterMount = commits
    const seen = new Set<string>()

    // Sample the glyph across many frame intervals (interval-agnostic).
    for (let i = 0; i < 20; i++) {
      act(() => {
        vi.advanceTimersByTime(50)
      })
      seen.add(span.textContent ?? '')
    }

    // The animation runs (more than one distinct glyph was shown)...
    expect(seen.size).toBeGreaterThan(1)
    // ...yet React committed ONLY the initial mount — zero per-frame re-renders.
    expect(commits).toBe(commitsAfterMount)
  })

  it('stays frozen while its pane is hidden (kept-alive inactive tab)', () => {
    vi.useFakeTimers()

    const { container } = render(
      <PaneVisibleContext.Provider value={false}>
        <GlyphSpinner spinner="braille" />
      </PaneVisibleContext.Provider>
    )

    const span = container.querySelector('[role="status"]') as HTMLElement
    const before = span.textContent

    act(() => {
      vi.advanceTimersByTime(1000)
    })

    expect(span.textContent).toBe(before)
  })
})
