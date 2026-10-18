import { useEffect, useState } from 'react'

import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useI18n } from '@/i18n'
import { activeGateway } from '@/store/gateway'
import type { SessionStats } from '@/types/jettstui'

interface SessionUsageDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  sessionId: string
  title?: string
}

/** Model working time + est cost + token/call breakdown for one session.
 *  Pulls from the `session.stats` gateway RPC, which reads the durable row, so
 *  it works for a session the user has never opened. */
export function SessionUsageDialog({ open, onOpenChange, sessionId, title }: SessionUsageDialogProps) {
  const { t } = useI18n()
  const u = t.sidebar.usage
  const [stats, setStats] = useState<null | SessionStats>(null)
  const [error, setError] = useState(false)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open || !sessionId) {
      return
    }

    let cancelled = false

    setStats(null)
    setError(false)
    setLoading(true)

    const gateway = activeGateway()

    if (!gateway) {
      setError(true)
      setLoading(false)

      return
    }

    gateway
      .request<SessionStats>('session.stats', { session_id: sessionId })
      .then(result => {
        if (!cancelled) {
          setStats(result)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError(true)
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [open, sessionId])

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{u.title}</DialogTitle>
        </DialogHeader>
        {title && <p className="-mt-1 truncate text-[length:var(--conversation-caption-font-size)] text-muted-foreground">{title}</p>}
        {loading && !stats ? (
          <p className="py-4 text-center text-[length:var(--conversation-caption-font-size)] text-muted-foreground">{u.loading}</p>
        ) : error || !stats ? (
          <p className="py-4 text-center text-[length:var(--conversation-caption-font-size)] text-muted-foreground">{u.unavailable}</p>
        ) : (
          <dl className="grid gap-2 py-1 text-[length:var(--conversation-caption-font-size)]">
            <HeroRow label={u.workingTime} value={formatDuration(stats.active_seconds)} />
            <HeroRow label={u.estCost} value={formatCost(stats, u)} />
            <div className="my-0.5 border-t border-(--ui-border)" />
            <Row label={u.model} value={stats.model || '—'} />
            <Row label={u.apiCalls} value={stats.api_call_count.toLocaleString()} />
            <Row label={u.toolCalls} value={stats.tool_call_count.toLocaleString()} />
            <Row label={u.tokensIn} value={formatTokens(stats.input_tokens)} />
            <Row label={u.tokensOut} value={formatTokens(stats.output_tokens)} />
            {stats.cache_read_tokens > 0 && <Row label={u.tokensCached} value={formatTokens(stats.cache_read_tokens)} />}
          </dl>
        )}
      </DialogContent>
    </Dialog>
  )
}

function HeroRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-semibold tabular-nums text-foreground">{value}</dd>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="tabular-nums text-foreground/90">{value}</dd>
    </div>
  )
}

function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds))

  if (s < 60) {
    return `${s}s`
  }

  const m = Math.floor(s / 60)

  if (m < 60) {
    return `${m}m ${s % 60}s`
  }

  const h = Math.floor(m / 60)

  return `${h}h ${m % 60}m`
}

function formatTokens(value: number): string {
  if (value < 1_000) {
    return String(value)
  }

  if (value < 1_000_000) {
    return `${(value / 1_000).toFixed(value < 10_000 ? 1 : 0)}K`
  }

  return `${(value / 1_000_000).toFixed(2)}M`
}

function formatCost(stats: SessionStats, u: { included: string; costUnknown: string }): string {
  if (stats.cost_status === 'included') {
    return u.included
  }

  if (stats.cost_usd === null || stats.cost_usd === undefined) {
    return u.costUnknown
  }

  if (stats.cost_usd === 0) {
    // Subscription-style providers (Antigravity, OpenAI OAuth) report no price.
    return stats.provider ? u.included : '$0.00'
  }

  return stats.cost_usd < 0.01 ? `<$0.01` : `$${stats.cost_usd.toFixed(stats.cost_usd < 1 ? 3 : 2)}`
}
