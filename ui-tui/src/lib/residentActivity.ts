import type { SessionActiveItem } from '../gatewayTypes.js'

/** Compact recency label: now | Nm | Nh | Nd. Empty when unknown or future. */
// The gateway reports `last_active` as Unix seconds (Python `time.time()`);
// anything below ~1973 in milliseconds is therefore a seconds value.
const SECONDS_CEILING = 1e11

export const relativeTime = (ts: number | undefined, now: number): string => {
  const ms = ts && ts < SECONDS_CEILING ? ts * 1000 : ts

  if (!ms || ms > now) {return ''}
  const delta = Math.max(0, now - ms)

  if (delta < 60_000) {return 'now'}

  if (delta < 3_600_000) {return `${Math.floor(delta / 60_000)}m`}

  if (delta < 86_400_000) {return `${Math.floor(delta / 3_600_000)}h`}

  return `${Math.floor(delta / 86_400_000)}d`
}

/** The N most recently active sessions, newest first. Display-order only —
 *  the sidebar keeps the gateway's creation order (see server.py note). */
export const commsSessions = (sessions: readonly SessionActiveItem[], count: number) =>
  [...sessions]
    .sort((a, b) => (b.last_active ?? 0) - (a.last_active ?? 0))
    .slice(0, Math.max(0, count))

export interface LastSeen {
  at: number
  messageCount: number
}

export type LastSeenMap = Map<string, LastSeen>

/** Unread delta for a session vs. its last-focused snapshot. Returns -1 when
 *  the count reset (resume/compaction) — renderers show that as a "changed"
 *  dot rather than a number, since a negative delta is meaningless. */
export const unreadCount = (session: SessionActiveItem, seen: LastSeen | undefined): number => {
  if (!seen) {return 0}
  const count = session.message_count ?? 0

  if (count < seen.messageCount) {return -1}

  return count - seen.messageCount
}

/** One pass over the 1.5s poll result: focus clears, growth on others
 *  accumulates. Returns fresh maps only when something actually changed so
 *  callers can skip a store write (and the full re-render it would cause). */
export const syncLastSeen = (
  prev: LastSeenMap,
  sessions: readonly SessionActiveItem[],
  focusedId: null | string,
  now: number
): { lastSeen: LastSeenMap; unread: Map<string, number> } => {
  const lastSeen: LastSeenMap = new Map(prev)
  const unread = new Map<string, number>()

  for (const session of sessions) {
    const isFocused = session.id === focusedId
    const seen = lastSeen.get(session.id)
    const delta = unreadCount(session, seen)

    if (isFocused || !seen || delta !== 0) {
      lastSeen.set(session.id, { at: now, messageCount: session.message_count ?? 0 })
    }

    unread.set(session.id, isFocused ? 0 : Math.max(0, delta))
  }

  return { lastSeen, unread }
}
