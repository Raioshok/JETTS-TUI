import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import { ProviderAccounts } from '@/app/settings/provider-accounts'
import { providerTitle } from '@/components/onboarding/providers'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { useI18n } from '@/i18n'
import { getProviderQuotas } from '@/jettstui'
import type { ProviderQuota, ProviderQuotaWindow } from '@/jettstui'
import { relativeTime } from '@/lib/time'

const QUOTA_STALE_MS = 60_000

/** Live subscription quota for every signed-in OAuth provider. */
export function ProviderQuotaSection() {
  const { t } = useI18n()
  const cc = t.commandCenter

  const query = useQuery({
    queryKey: ['provider-quota'],
    queryFn: getProviderQuotas,
    staleTime: QUOTA_STALE_MS
  })

  const providers = query.data?.providers ?? []

  return (
    <section>
      <div className="mb-2 flex items-baseline justify-between">
        <span className="text-[0.625rem] font-medium uppercase tracking-[0.08em] text-(--ui-text-tertiary)">
          {cc.providerQuota}
        </span>
        <Button disabled={query.isFetching} onClick={() => void query.refetch()} size="xs" variant="text">
          {cc.quotaRefresh}
        </Button>
      </div>
      {query.isPending ? (
        <Caption>{cc.quotaLoading}</Caption>
      ) : query.isError ? (
        <Caption>{cc.quotaUnavailable}</Caption>
      ) : providers.length === 0 ? (
        <Caption>{cc.quotaNone}</Caption>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2">
          {providers.map(provider => (
            <ProviderQuotaCard key={provider.id} provider={provider} />
          ))}
        </ul>
      )}
    </section>
  )
}

function ProviderQuotaCard({ provider }: { provider: ProviderQuota }) {
  const { t } = useI18n()
  const cc = t.commandCenter
  const windows = provider.windows ?? []

  const note = !provider.supported
    ? cc.quotaNotReported
    : provider.error || provider.unavailable_reason || (windows.length === 0 ? cc.quotaUnavailable : '')

  return (
    <li className="min-w-0">
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate text-[length:var(--conversation-text-font-size)] font-medium text-foreground">
          {providerTitle(provider)}
        </span>
        {provider.plan && <span className="shrink-0 text-[0.65rem] text-(--ui-text-tertiary)">{provider.plan}</span>}
      </div>
      {provider.account && (provider.account_count ?? 0) > 1 && (
        <div className="truncate text-[0.65rem] text-(--ui-text-tertiary)">{provider.account}</div>
      )}
      {note ? (
        <Caption>{note}</Caption>
      ) : (
        <ul className="mt-1.5 grid gap-2">
          {windows.map(quota => (
            <QuotaWindowRow key={quota.label} quota={quota} />
          ))}
        </ul>
      )}
      {(provider.details ?? []).map(detail => (
        <Caption key={detail}>{detail}</Caption>
      ))}
      {(provider.account_count ?? 0) > 1 && (
        <div className="mt-2">
          <ProviderAccounts compact providerId={provider.id} />
        </div>
      )}
    </li>
  )
}

function QuotaWindowRow({ quota }: { quota: ProviderQuotaWindow }) {
  const { t } = useI18n()
  const cc = t.commandCenter
  const used = Math.min(100, Math.max(0, quota.used_percent ?? 0))
  const resetMs = quota.reset_at ? Date.parse(quota.reset_at) : Number.NaN

  return (
    <li className="min-w-0">
      <div className="mb-1 flex items-baseline justify-between gap-2 text-[0.65rem]">
        <span className="min-w-0 truncate text-foreground">{quota.label}</span>
        <span className="shrink-0 text-(--ui-text-tertiary)">
          {cc.quotaUsed(`${Math.round(used)}%`)}
          {Number.isFinite(resetMs) && ` · ${cc.quotaResets(relativeTime(resetMs))}`}
        </span>
      </div>
      <Progress destructive={used >= 90} size="sm" value={used / 100} />
    </li>
  )
}

function Caption({ children }: { children: ReactNode }) {
  return <div className="text-[length:var(--conversation-caption-font-size)] text-(--ui-text-tertiary)">{children}</div>
}
