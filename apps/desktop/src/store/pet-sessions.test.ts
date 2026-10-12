import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ClientSessionState } from '@/app/types'
import { en } from '@/i18n/en'
import type { SessionInfo } from '@/types/jettstui'

import {
  $petSessionFeed,
  buildPetSessionFeed,
  formatPetElapsed,
  openPetSession,
  PET_SESSION_FEED_LIMIT,
  petSessionFeedLabels,
  setPetSessionFeedEnabled,
  setPetSessionOpener
} from './pet-sessions'
import { $sessions, $unreadFinishedSessionIds } from './session'
import { clearAllSessionStates, publishSessionState, setSessionStalled } from './session-states'

function state(storedSessionId: null | string, patch: Partial<ClientSessionState> = {}): ClientSessionState {
  return { busy: false, needsInput: false, storedSessionId, turnStartedAt: null, ...patch } as ClientSessionState
}

function session(id: string, title: null | string, preview: null | string = null): SessionInfo {
  return { id, preview, title } as SessionInfo
}

afterEach(() => {
  clearAllSessionStates()
  $unreadFinishedSessionIds.set([])
  $sessions.set([])
  setPetSessionFeedEnabled(true)
  setPetSessionOpener(null)
})

describe('buildPetSessionFeed', () => {
  it('orders needs-input, working, stalled, then finished, and titles from the session list', () => {
    const feed = buildPetSessionFeed({
      sessions: [session('a', 'Refactor auth'), session('b', null, 'fix the  build'), session('c', 'Docs')],
      stalledIds: ['c'],
      states: {
        r1: state('a', { busy: true, turnStartedAt: 100 }),
        r2: state('b', { busy: true, needsInput: true, turnStartedAt: 50 }),
        r3: state('c', { busy: true, turnStartedAt: 10 })
      },
      unreadFinishedIds: ['d']
    })

    expect(feed.map(item => [item.id, item.status])).toEqual([
      ['b', 'needs-input'],
      ['a', 'working'],
      ['c', 'stalled'],
      ['d', 'finished']
    ])
    expect(feed[0].title).toBe('fix the build')
    expect(feed[1].title).toBe('Refactor auth')
    expect(feed[3].title).toBe('')
  })

  it('skips idle sessions and runtimes without a stored id', () => {
    const feed = buildPetSessionFeed({
      sessions: [],
      stalledIds: [],
      states: { r1: state('a'), r2: state(null, { busy: true }) },
      unreadFinishedIds: []
    })

    expect(feed).toEqual([])
  })

  it('keeps the most urgent status when two runtimes share a stored id', () => {
    const feed = buildPetSessionFeed({
      sessions: [],
      stalledIds: [],
      states: { r1: state('a', { busy: true }), r2: state('a', { needsInput: true }) },
      unreadFinishedIds: ['a']
    })

    expect(feed).toHaveLength(1)
    expect(feed[0].status).toBe('needs-input')
  })

  it('lists the newest finish first and caps the feed', () => {
    const ids = Array.from({ length: PET_SESSION_FEED_LIMIT + 3 }, (_, i) => `s${i}`)
    const feed = buildPetSessionFeed({ sessions: [], stalledIds: [], states: {}, unreadFinishedIds: ids })

    expect(feed).toHaveLength(PET_SESSION_FEED_LIMIT)
    expect(feed[0].id).toBe(ids[ids.length - 1])
  })
})

describe('$petSessionFeed', () => {
  it('follows live session signals and keeps its reference across no-op publishes', () => {
    $sessions.set([session('a', 'Ship it')])
    publishSessionState('r1', state('a', { busy: true, turnStartedAt: 5 }))

    const first = $petSessionFeed.get()
    expect(first).toEqual([{ id: 'a', startedAt: 5, status: 'working', title: 'Ship it' }])

    // A token delta republishes the state object without changing anything the feed shows.
    publishSessionState('r1', state('a', { busy: true, turnStartedAt: 5 }))
    expect($petSessionFeed.get()).toBe(first)

    setSessionStalled('a', true)
    expect($petSessionFeed.get()[0].status).toBe('stalled')
  })

  it('is empty while the feed is turned off', () => {
    publishSessionState('r1', state('a', { needsInput: true }))
    setPetSessionFeedEnabled(false)

    expect($petSessionFeed.get()).toEqual([])
  })
})

describe('openPetSession', () => {
  it('routes through the registered opener and is a no-op without one', () => {
    const opener = vi.fn()

    openPetSession('a')
    setPetSessionOpener(opener)
    openPetSession('b')

    expect(opener).toHaveBeenCalledExactlyOnceWith('b')
  })
})

describe('labels and elapsed', () => {
  it('maps every status to localized copy', () => {
    const labels = petSessionFeedLabels(en.petSessions)

    expect(Object.values(labels.status).every(Boolean)).toBe(true)
    expect(labels.more).toContain('{count}')
  })

  it('formats elapsed turn time compactly', () => {
    expect(formatPetElapsed(null, 10_000)).toBe('')
    expect(formatPetElapsed(0, 45_000)).toBe('')
    expect(formatPetElapsed(1_000, 46_000)).toBe('45s')
    expect(formatPetElapsed(1_000, 1_000 + 12 * 60_000)).toBe('12m')
    expect(formatPetElapsed(1_000, 1_000 + 2 * 3_600_000)).toBe('2h')
  })
})
