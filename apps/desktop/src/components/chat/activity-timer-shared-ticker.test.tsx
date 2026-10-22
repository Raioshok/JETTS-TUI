import { render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { __resetElapsedTimerRegistryForTests, useElapsedSeconds } from '@/components/chat/activity-timer'

function Timer({ timerKey }: { timerKey: string }) {
  const seconds = useElapsedSeconds(true, timerKey)

  return <span data-testid={timerKey}>{seconds}</span>
}

/**
 * Many live elapsed readouts (a fan-out of subagent rows, message ages, status
 * lines) used to each run their own setInterval. They now share ONE 1 Hz
 * ticker, so a burst of concurrent timers costs a single wakeup/sec, with the
 * interval released once the last timer unmounts. Displayed values are
 * unchanged — see activity-timer.test.tsx for value behavior.
 */
describe('useElapsedSeconds shared ticker', () => {
  afterEach(() => {
    __resetElapsedTimerRegistryForTests()
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('drives N concurrent live timers from a single 1s interval', () => {
    vi.useFakeTimers()
    const setInterval = vi.spyOn(window, 'setInterval')

    render(
      <>
        <Timer timerKey="a" />
        <Timer timerKey="b" />
        <Timer timerKey="c" />
        <Timer timerKey="d" />
      </>
    )

    const oneSecondIntervals = setInterval.mock.calls.filter(([, ms]) => ms === 1000).length
    expect(oneSecondIntervals).toBe(1)
  })

  it('clears the shared interval once the last timer unmounts', () => {
    vi.useFakeTimers()
    const clearInterval = vi.spyOn(window, 'clearInterval')

    const { unmount } = render(
      <>
        <Timer timerKey="x" />
        <Timer timerKey="y" />
      </>
    )

    unmount()

    expect(clearInterval).toHaveBeenCalled()
  })
})
