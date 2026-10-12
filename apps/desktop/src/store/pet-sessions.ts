import { atom, computed } from 'nanostores'

import type { ClientSessionState } from '@/app/types'
import type { Translations } from '@/i18n/types'
import { persistBoolean, storedBoolean } from '@/lib/storage'
import type { SessionInfo } from '@/types/jettstui'

import { $sessions, $unreadFinishedSessionIds } from './session'
import { $sessionStates, $stalledSessionIds } from './session-states'

/**
 * The pet's "what are my sessions doing" feed (Codex-pets style).
 *
 * While a pet is out, it keeps a small stack of cards above itself — one per
 * session that is waiting on you, working, gone quiet, or finished while you
 * weren't looking — so a glance at the mascot replaces scanning the sidebar.
 * Clicking a card opens that session.
 *
 * Pure projection of the same session signals the sidebar dots read
 * (`$sessionStates`, `$stalledSessionIds`, `$unreadFinishedSessionIds`), so the
 * feed and the sidebar can never disagree. Both the in-window pet and the
 * popped-out overlay render it; the overlay gets it pushed over IPC.
 */

export type PetSessionStatus = 'needs-input' | 'working' | 'stalled' | 'finished'

export interface PetSessionFeedItem {
  /** Stored (durable) session id — what navigation keys off. */
  id: string
  /** Session title or preview; empty when the session has neither yet. */
  title: string
  status: PetSessionStatus
  /** Epoch ms the running turn started (working/stalled/needs-input), else null. */
  startedAt: null | number
}

/** Localized strings for the feed. The overlay window has no i18n provider, so
 *  the main renderer resolves these and ships them with the items. */
export interface PetSessionFeedLabels {
  status: Record<PetSessionStatus, string>
  untitled: string
  more: string
  heading: string
}

/** Shape the localized `petSessions` copy into the serializable label bag. */
export function petSessionFeedLabels(copy: Translations['petSessions']): PetSessionFeedLabels {
  return {
    heading: copy.heading,
    more: copy.moreCount,
    status: {
      finished: copy.finished,
      'needs-input': copy.needsInput,
      stalled: copy.stalled,
      working: copy.working
    },
    untitled: copy.untitled
  }
}

// Waiting on you outranks everything; finished-unread trails because it's the
// only entry that isn't live.
const STATUS_RANK: Record<PetSessionStatus, number> = {
  'needs-input': 0,
  working: 1,
  stalled: 2,
  finished: 3
}

/** Most entries the feed ever carries (the view shows fewer plus "+N"). */
export const PET_SESSION_FEED_LIMIT = 8

export interface PetSessionFeedInput {
  states: Record<string, ClientSessionState>
  stalledIds: readonly string[]
  unreadFinishedIds: readonly string[]
  sessions: readonly SessionInfo[]
}

function sessionTitle(session: SessionInfo | undefined): string {
  return (session?.title?.trim() || session?.preview?.trim() || '').replace(/\s+/g, ' ')
}

export function buildPetSessionFeed({
  states,
  stalledIds,
  unreadFinishedIds,
  sessions
}: PetSessionFeedInput): PetSessionFeedItem[] {
  const byId = new Map(sessions.map(session => [session.id, session]))
  const stalled = new Set(stalledIds)
  const items = new Map<string, PetSessionFeedItem>()

  for (const state of Object.values(states)) {
    const id = state.storedSessionId

    if (!id) {
      continue
    }

    const status: null | PetSessionStatus = state.needsInput
      ? 'needs-input'
      : state.busy
        ? stalled.has(id)
          ? 'stalled'
          : 'working'
        : null

    if (!status) {
      continue
    }

    const existing = items.get(id)

    // Two runtimes can briefly map to one stored id; keep the most urgent.
    if (!existing || STATUS_RANK[status] < STATUS_RANK[existing.status]) {
      items.set(id, { id, startedAt: state.turnStartedAt ?? null, status, title: sessionTitle(byId.get(id)) })
    }
  }

  // Newest finish first.
  for (const id of [...unreadFinishedIds].reverse()) {
    if (!items.has(id)) {
      items.set(id, { id, startedAt: null, status: 'finished', title: sessionTitle(byId.get(id)) })
    }
  }

  return [...items.values()]
    .sort((a, b) => STATUS_RANK[a.status] - STATUS_RANK[b.status] || (a.startedAt ?? 0) - (b.startedAt ?? 0))
    .slice(0, PET_SESSION_FEED_LIMIT)
}

function sameFeed(a: readonly PetSessionFeedItem[], b: readonly PetSessionFeedItem[]): boolean {
  return (
    a.length === b.length &&
    a.every(
      (item, i) =>
        item.id === b[i].id &&
        item.status === b[i].status &&
        item.title === b[i].title &&
        item.startedAt === b[i].startedAt
    )
  )
}

/**
 * Opt-out: show the session feed next to the pet. Pure client presentation, so
 * it lives in localStorage beside the roam toggle — per-device, not per-profile.
 */
const FEED_KEY = 'jettstui.desktop.pet-session-feed.v1'
export const $petSessionFeedEnabled = atom<boolean>(storedBoolean(FEED_KEY, true))

export const setPetSessionFeedEnabled = (on: boolean) => {
  $petSessionFeedEnabled.set(on)
  persistBoolean(FEED_KEY, on)
}

const EMPTY: PetSessionFeedItem[] = []
let lastFeed: PetSessionFeedItem[] = EMPTY

/**
 * The live feed. `$sessionStates` republishes on every streamed token, so keep
 * the previous array when nothing visible changed — otherwise every token would
 * re-render the pet and (when popped out) cross the IPC boundary.
 */
export const $petSessionFeed = computed(
  [$petSessionFeedEnabled, $sessionStates, $stalledSessionIds, $unreadFinishedSessionIds, $sessions],
  (enabled, states, stalledIds, unreadFinishedIds, sessions): PetSessionFeedItem[] => {
    const next = enabled ? buildPetSessionFeed({ sessions, stalledIds, states, unreadFinishedIds }) : EMPTY

    if (sameFeed(lastFeed, next)) {
      return lastFeed
    }

    lastFeed = next

    return next
  }
)

/** Opens a session from a feed card. Registered by the app wiring (it owns
 *  navigation); the pet surfaces stay free of router knowledge. */
let opener: ((storedSessionId: string) => void) | null = null

export function setPetSessionOpener(fn: ((storedSessionId: string) => void) | null): void {
  opener = fn
}

export function openPetSession(storedSessionId: string): void {
  opener?.(storedSessionId)
}

/** Compact elapsed label for a running turn: 45s, 12m, 2h. */
export function formatPetElapsed(startedAt: null | number, now: number): string {
  if (!startedAt) {
    return ''
  }

  const seconds = Math.max(0, Math.floor((now - startedAt) / 1000))

  if (seconds < 60) {
    return `${seconds}s`
  }

  const minutes = Math.floor(seconds / 60)

  return minutes < 60 ? `${minutes}m` : `${Math.floor(minutes / 60)}h`
}
