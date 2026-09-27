import { describe, expect, it } from 'vitest'

import type { SessionActiveItem } from '../gatewayTypes.js'
import { commsSessions, relativeTime, syncLastSeen, unreadCount } from '../lib/residentActivity.js'

const sess = (id: string, lastActive?: number, status: SessionActiveItem['status'] = 'idle'): SessionActiveItem =>
  ({ id, last_active: lastActive, status })

describe('relativeTime', () => {
  const now = 1_000_000

  it('renders fresh, minutes, hours, and days', () => {
    expect(relativeTime(now, now)).toBe('now')
    expect(relativeTime(now - 5 * 60_000, now)).toBe('5m')
    expect(relativeTime(now - 3 * 3_600_000, now)).toBe('3h')
    expect(relativeTime(now - 2 * 86_400_000, now)).toBe('2d')
  })

  it('returns empty string for missing or future timestamps', () => {
    expect(relativeTime(undefined, now)).toBe('')
    expect(relativeTime(now + 1, now)).toBe('')
  })
})

describe('commsSessions', () => {
  it('picks the N most recently active, newest first', () => {
    const sessions = [sess('a', 100), sess('b', 900), sess('c', 500)]
    expect(commsSessions(sessions, 2).map(s => s.id)).toEqual(['b', 'c'])
  })

  it('never exceeds the source list', () => {
    expect(commsSessions([], 3)).toEqual([])
  })

  it('treats missing last_active as zero (oldest)', () => {
    const sessions = [sess('a', undefined), sess('b', 100)]
    expect(commsSessions(sessions, 1).map(s => s.id)).toEqual(['b'])
  })
})

describe('unread tracking', () => {
  const now = 1_000_000

  const s = (id: string, count: number): SessionActiveItem =>
    ({ id, message_count: count, status: 'idle' })

  it('first sighting of a session is never unread', () => {
    const { lastSeen, unread } = syncLastSeen(new Map(), [s('a', 5)], 'a', now)
    expect(unread.get('a')).toBe(0)
    expect(lastSeen.get('a')?.messageCount).toBe(5)
  })

  it('background session growth becomes unread', () => {
    const seen = new Map([['a', { messageCount: 5, at: now - 1000 }]])
    const { unread } = syncLastSeen(seen, [s('a', 8)], 'focused', now)
    expect(unread.get('a')).toBe(3)
  })

  it('the focused session is always marked seen', () => {
    const seen = new Map([['a', { messageCount: 5, at: now - 1000 }]])
    const { unread } = syncLastSeen(seen, [s('a', 9)], 'a', now)
    expect(unread.get('a')).toBe(0)
  })

  it('unreadCount signals a count reset with -1', () => {
    const seen = { messageCount: 9, at: now - 1000 }
    expect(unreadCount(s('a', 2), seen)).toBe(-1)
    expect(unreadCount(s('a', 9), seen)).toBe(0)
  })

  it('keeps prior unseen state for a session that is not in this poll', () => {
    const seen = new Map([['gone', { messageCount: 3, at: now - 1000 }]])
    const { lastSeen } = syncLastSeen(seen, [], 'focused', now)
    expect(lastSeen.get('gone')?.messageCount).toBe(3)
  })
})
