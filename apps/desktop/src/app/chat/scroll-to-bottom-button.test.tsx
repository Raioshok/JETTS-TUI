import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { clearAllPrompts, setApprovalRequest } from '@/store/prompts'
import { $activeSessionId } from '@/store/session'
import { onScrollToBottomRequest, resetThreadScroll, setThreadAtBottom } from '@/store/thread-scroll'

import { type ComposerScope, ComposerScopeProvider, MAIN_COMPOSER_SCOPE } from './composer/scope'
import { ScrollToBottomButton } from './scroll-to-bottom-button'

const TILE_SCOPE: ComposerScope = { ...MAIN_COMPOSER_SCOPE, target: 'tile:other' }

function pendingApproval(sessionId = 'sess-1') {
  $activeSessionId.set('sess-1')
  setApprovalRequest({ command: 'rm -rf /tmp/x', description: 'dangerous command', sessionId })
}

afterEach(() => {
  cleanup()
  clearAllPrompts()
  resetThreadScroll('main')
  resetThreadScroll(TILE_SCOPE.target)
  $activeSessionId.set(null)
})

// `getByRole('button')` excludes aria-hidden nodes, so "queryByRole null" is the
// control's hidden (parked-at-bottom) state.
describe('ScrollToBottomButton', () => {
  it('stays hidden while parked at the bottom', () => {
    render(<ScrollToBottomButton sessionId="sess-1" />)

    expect(screen.queryByRole('button')).toBeNull()
  })

  it('is a plain jump-to-bottom control when scrolled up with no approval', () => {
    setThreadAtBottom('main', false)
    render(<ScrollToBottomButton sessionId="sess-1" />)

    expect(screen.getByRole('button', { name: 'Scroll to bottom' })).toBeTruthy()
    expect(screen.queryByText('Approval needed')).toBeNull()
  })

  it('morphs into the approval pill when scrolled up with a pending approval', () => {
    pendingApproval()
    setThreadAtBottom('main', false)
    render(<ScrollToBottomButton sessionId="sess-1" />)

    expect(screen.getByRole('button', { name: 'Approval needed' })).toBeTruthy()
    expect(screen.getByText('Approval needed')).toBeTruthy()
  })

  it('does not morph while a pending approval is still in view (at bottom)', () => {
    pendingApproval()
    render(<ScrollToBottomButton sessionId="sess-1" />)

    // Parked at bottom → control hidden, so it can't claim "approval needed".
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('re-arms sticky-bottom on click', () => {
    const handler = vi.fn()
    const stop = onScrollToBottomRequest('main', handler)
    setThreadAtBottom('main', false)
    render(<ScrollToBottomButton sessionId="sess-1" />)

    fireEvent.click(screen.getByRole('button'))

    expect(handler).toHaveBeenCalledTimes(1)
    stop()
  })

  it('only reacts to its own pane and its own session', () => {
    const mainHandler = vi.fn()
    const tileHandler = vi.fn()
    const stops = [onScrollToBottomRequest('main', mainHandler), onScrollToBottomRequest(TILE_SCOPE.target, tileHandler)]

    // Another chat's approval, and only the tile is scrolled up.
    pendingApproval('sess-1')
    setThreadAtBottom(TILE_SCOPE.target, false)
    render(
      <ComposerScopeProvider value={TILE_SCOPE}>
        <ScrollToBottomButton sessionId="sess-2" />
      </ComposerScopeProvider>
    )

    expect(screen.queryByText('Approval needed')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Scroll to bottom' }))
    expect(tileHandler).toHaveBeenCalledTimes(1)
    expect(mainHandler).not.toHaveBeenCalled()
    stops.forEach(stop => stop())
  })
})
