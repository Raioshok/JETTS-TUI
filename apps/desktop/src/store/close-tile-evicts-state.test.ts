import { afterEach, describe, expect, it } from 'vitest'

import { createClientSessionState } from '@/lib/chat-runtime'
import {
  $sessionStates,
  $sessionTiles,
  clearAllSessionStates,
  closeSessionTile,
  publishSessionState
} from '@/store/session-states'

/**
 * Closing a tab used to leave its cached runtime state resident in
 * `$sessionStates` for the whole app session. Because `publishSessionState`
 * spreads the entire Record on every streaming delta, a growing pile of
 * dead-tab states made every OTHER session's per-token publish cost more —
 * the "heavy over time" the user reported. `closeSessionTile` now evicts the
 * closed tab's state, but only when the session is idle: a still-busy session
 * stays resident so a backgrounded turn keeps its sidebar "working" state and
 * a ⌘⇧T reopen shows live progress.
 */
describe('closeSessionTile eviction', () => {
  afterEach(() => {
    clearAllSessionStates()
    $sessionTiles.set([])
  })

  it('drops an idle closed tab\'s cached state', () => {
    $sessionTiles.set([{ runtimeId: 'r1', storedSessionId: 's1' }])
    publishSessionState('r1', { ...createClientSessionState('s1'), busy: false })
    expect($sessionStates.get().r1).toBeDefined()

    closeSessionTile('s1')

    expect($sessionStates.get().r1).toBeUndefined()
    expect($sessionTiles.get()).toEqual([])
  })

  it('keeps a still-busy session resident across the close', () => {
    $sessionTiles.set([{ runtimeId: 'r2', storedSessionId: 's2' }])
    publishSessionState('r2', { ...createClientSessionState('s2'), busy: true })
    expect($sessionStates.get().r2).toBeDefined()

    closeSessionTile('s2')

    expect($sessionStates.get().r2).toBeDefined()
    expect($sessionTiles.get()).toEqual([])
  })

  it('is a no-op on state when the tile never bound a runtime id', () => {
    $sessionTiles.set([{ storedSessionId: 's3' }])

    expect(() => closeSessionTile('s3')).not.toThrow()
    expect($sessionTiles.get()).toEqual([])
  })
})
