import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import { useI18n } from '@/i18n'
import { listOAuthAccounts, removeOAuthAccount, switchOAuthAccount } from '@/jettstui'
import { Check, Loader2, Plus, Trash2 } from '@/lib/icons'
import { relativeTime } from '@/lib/time'
import { cn } from '@/lib/utils'
import { notify, notifyError } from '@/store/notifications'
import type { OAuthAccount } from '@/types/jettstui'

export const oauthAccountsKey = (providerId: string) => ['oauth-accounts', providerId] as const

interface ProviderAccountsProps {
  /** Compact = switch only (Usage tab); full adds remove + "Add account". */
  compact?: boolean
  onAddAccount?: () => void
  providerId: string
}

/**
 * Saved sign-in accounts for one OAuth provider, with one-click switching.
 * Switching moves new and open chats onto the account (open chats on their
 * next message); when the account in use runs out of quota the backend
 * rotates to the next one by itself.
 */
export function ProviderAccounts({ compact = false, onAddAccount, providerId }: ProviderAccountsProps) {
  const { t } = useI18n()
  const copy = t.settings.providers.accounts
  const queryClient = useQueryClient()

  const query = useQuery({
    queryKey: oauthAccountsKey(providerId),
    queryFn: () => listOAuthAccounts(providerId)
  })

  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: oauthAccountsKey(providerId) }),
      queryClient.invalidateQueries({ queryKey: ['provider-quota'] })
    ])

  const switchTo = useMutation({
    mutationFn: (account: OAuthAccount) => switchOAuthAccount(providerId, account.id),
    onSuccess: ({ account }) => {
      notify({ durationMs: 3_000, kind: 'success', title: copy.switchedTitle, message: copy.switched(account.label) })
      void refresh()
    },
    onError: error => notifyError(error, copy.failedSwitch)
  })

  const remove = useMutation({
    mutationFn: (account: OAuthAccount) => removeOAuthAccount(providerId, account.id),
    onSuccess: () => void refresh(),
    onError: error => notifyError(error, copy.failedRemove)
  })

  const accounts = query.data?.accounts ?? []

  if (compact && accounts.length < 2) {
    return null
  }

  const busyId = (switchTo.isPending && switchTo.variables?.id) || (remove.isPending && remove.variables?.id) || null

  const confirmRemove = (account: OAuthAccount) => {
    if (window.confirm(copy.removeConfirm(account.label))) {
      remove.mutate(account)
    }
  }

  return (
    <div className={cn('grid gap-1', !compact && 'px-3 pb-2.5')}>
      {!compact && accounts.length > 1 && (
        <p className="text-[0.68rem] leading-5 text-muted-foreground/80">{copy.autoSwitchHint}</p>
      )}
      <ul aria-label={copy.title} className="grid gap-0.5">
        {accounts.map(account => (
          <AccountRow
            account={account}
            busy={busyId === account.id}
            compact={compact}
            key={account.id}
            onRemove={() => confirmRemove(account)}
            onUse={() => switchTo.mutate(account)}
          />
        ))}
      </ul>
      {!compact && onAddAccount && (
        <div>
          <Button onClick={onAddAccount} size="xs" type="button" variant="ghost">
            <Plus />
            {copy.add}
          </Button>
        </div>
      )}
    </div>
  )
}

function AccountRow({
  account,
  busy,
  compact,
  onRemove,
  onUse
}: {
  account: OAuthAccount
  busy: boolean
  compact: boolean
  onRemove: () => void
  onUse: () => void
}) {
  const { t } = useI18n()
  const copy = t.settings.providers.accounts

  const status =
    account.status === 'verify'
      ? copy.needsVerification
      : account.status === 'dead'
        ? copy.signInAgain
        : account.status === 'exhausted'
          ? account.exhausted_until
            ? copy.outOfQuotaUntil(relativeTime(account.exhausted_until * 1000))
            : copy.outOfQuota
          : null

  return (
    <li className="flex min-w-0 items-center gap-2 text-[length:var(--conversation-caption-font-size)]">
      <span className="min-w-0 flex-1 truncate">
        <span className={cn('text-foreground', account.active && 'font-medium')}>{account.label}</span>
        {!compact && account.detail && <span className="ml-1.5 text-muted-foreground">{account.detail}</span>}
        {status && <span className="ml-1.5 text-(--ui-text-tertiary)">· {status}</span>}
      </span>
      {account.status === 'verify' && account.verify_url && (
        <Button
          onClick={() => window.open(account.verify_url ?? '', '_blank', 'noopener,noreferrer')}
          size="xs"
          type="button"
          variant="outline"
        >
          {copy.verify}
        </Button>
      )}
      {account.active ? (
        <span className="inline-flex shrink-0 items-center gap-1 bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
          <Check className="size-3" />
          {copy.inUse}
        </span>
      ) : (
        <Button disabled={busy} onClick={onUse} size="xs" type="button" variant="outline">
          {busy ? <Loader2 className="animate-spin" /> : null}
          {copy.use}
        </Button>
      )}
      {!compact && (
        <Button
          aria-label={`${t.common.remove} ${account.label}`}
          disabled={busy}
          onClick={onRemove}
          size="icon-xs"
          title={`${t.common.remove} ${account.label}`}
          type="button"
          variant="ghost"
        >
          <Trash2 className="size-3" />
        </Button>
      )}
    </li>
  )
}
