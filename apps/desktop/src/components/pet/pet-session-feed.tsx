import { useEffect, useState } from 'react'

import {
  formatPetElapsed,
  type PetSessionFeedItem,
  type PetSessionFeedLabels,
  type PetSessionStatus
} from '@/store/pet-sessions'

/**
 * Stack of session cards that rides above the pet (Codex-pets style): one row
 * per session waiting on you, working, gone quiet, or finished unseen. Clicking
 * a row opens that session.
 *
 * Presentational only — items and labels come in as props so the in-window pet
 * (reads atoms + i18n) and the gateway-less overlay (gets them over IPC) render
 * the exact same thing. Inline styles match the rest of the pet chrome, which
 * also has to render in the bare overlay window.
 */

const VISIBLE_ROWS = 3

const DOT_COLOR: Record<PetSessionStatus, string> = {
  'needs-input': 'var(--ui-yellow)',
  working: 'var(--ui-accent)',
  stalled: 'var(--ui-text-quaternary)',
  finished: 'var(--ui-green)'
}

interface PetSessionFeedProps {
  items: readonly PetSessionFeedItem[]
  labels: PetSessionFeedLabels
  onOpen: (storedSessionId: string) => void
  /** Which edge of the pet the stack hugs, so it never runs off-screen. */
  align?: 'center' | 'end' | 'start'
}

function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (!active) {
      return
    }

    setNow(Date.now())
    const id = window.setInterval(() => setNow(Date.now()), 5000)

    return () => window.clearInterval(id)
  }, [active])

  return now
}

export function PetSessionFeed({ items, labels, onOpen, align = 'center' }: PetSessionFeedProps) {
  const ticking = items.some(item => item.status === 'working' || item.status === 'stalled')
  const now = useNow(ticking)

  if (!items.length) {
    return null
  }

  const visible = items.slice(0, VISIBLE_ROWS)
  const hidden = items.length - visible.length

  return (
    <div
      aria-label={labels.heading}
      role="list"
      style={{
        alignItems: align === 'start' ? 'flex-start' : align === 'end' ? 'flex-end' : 'center',
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
        pointerEvents: 'auto'
      }}
    >
      {visible.map(item => {
        const title = item.title || labels.untitled
        const elapsed = item.status === 'finished' ? '' : formatPetElapsed(item.startedAt, now)

        return (
          <button
            data-pet-session-row={item.status}
            key={item.id}
            onClick={() => onOpen(item.id)}
            onPointerDown={e => e.stopPropagation()}
            onPointerUp={e => e.stopPropagation()}
            role="listitem"
            style={{
              alignItems: 'center',
              background: 'var(--ui-bg-elevated)',
              border: '1px solid var(--ui-stroke-secondary)',
              borderRadius: 8,
              boxShadow: '0 4px 14px rgba(0,0,0,0.22)',
              color: 'var(--foreground)',
              cursor: 'pointer',
              display: 'inline-flex',
              font: 'inherit',
              fontSize: 11,
              gap: 6,
              lineHeight: 1.2,
              maxWidth: 220,
              padding: '4px 8px',
              textAlign: 'left',
              whiteSpace: 'nowrap'
            }}
            title={`${title} · ${labels.status[item.status]}`}
            type="button"
          >
            <span
              aria-hidden
              className={item.status === 'working' || item.status === 'needs-input' ? 'animate-pulse' : undefined}
              style={{
                background: DOT_COLOR[item.status],
                borderRadius: 999,
                flexShrink: 0,
                height: 7,
                width: 7
              }}
            />
            <span style={{ fontWeight: 500, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' }}>{title}</span>
            <span style={{ color: 'var(--ui-text-tertiary)', flexShrink: 0 }}>
              {labels.status[item.status]}
              {elapsed ? ` · ${elapsed}` : ''}
            </span>
          </button>
        )
      })}
      {hidden > 0 && (
        <span
          style={{
            background: 'var(--ui-bg-elevated)',
            border: '1px solid var(--ui-stroke-secondary)',
            borderRadius: 999,
            color: 'var(--ui-text-tertiary)',
            fontSize: 10,
            lineHeight: 1,
            padding: '3px 7px'
          }}
        >
          {labels.more.replace('{count}', String(hidden))}
        </span>
      )}
    </div>
  )
}
