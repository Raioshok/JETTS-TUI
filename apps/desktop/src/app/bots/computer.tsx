import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import { FieldHint } from '@/components/ui/field'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useI18n } from '@/i18n'
import { notifyError } from '@/store/notifications'

import { useGatewayRequest } from '../gateway/hooks/use-gateway-request'

/** Select value for "no computer" — never a valid VM name. */
const NO_COMPUTER = '__none__'

interface BotComputer {
  computer: null | string
  vms: string[]
}

interface BotsComputerProps {
  enabled: boolean
  profile: string
}

/** The VM the Bots share as their own computer, and a way to open it (to sign in for them). */
export function BotsComputer({ enabled, profile }: BotsComputerProps) {
  const { t } = useI18n()
  const b = t.bots
  const { requestGateway } = useGatewayRequest()
  const queryClient = useQueryClient()
  const queryKey = ['bots-computer', profile] as const

  // Discovery asks every hypervisor, so it is slower than the roster; load it separately.
  const computer = useQuery({
    queryKey,
    queryFn: () => requestGateway<BotComputer>('bots.computer', { profile }),
    enabled
  })

  const choose = useMutation({
    mutationFn: (name: null | string) => requestGateway<BotComputer>('bots.set_computer', { profile, computer: name }),
    onError: error => notifyError(error, b.computerSaveFailed),
    onSuccess: ({ computer: saved }) =>
      queryClient.setQueryData<BotComputer>(queryKey, current => (current ? { ...current, computer: saved } : current))
  })

  const open = useMutation({
    mutationFn: () => requestGateway('bots.open_computer', { profile }),
    onError: error => notifyError(error, b.openComputerFailed)
  })

  const current = computer.data?.computer ?? null
  // Keep a configured VM selectable even when discovery can't see it right now.
  const names = [...new Set([...(computer.data?.vms ?? []), ...(current ? [current] : [])])]

  return (
    <section className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start sm:gap-6">
      <div className="grid gap-1">
        <span className="text-sm font-medium text-(--ui-text-primary)" id="bots-computer">
          {b.computerTitle}
        </span>
        <FieldHint>{current ? b.computerHint(current) : b.computerNoneHint}</FieldHint>
      </div>
      <div aria-labelledby="bots-computer" className="flex items-center gap-2" role="group">
        <Select
          disabled={!computer.data || choose.isPending}
          onValueChange={value => choose.mutate(value === NO_COMPUTER ? null : value)}
          value={current ?? NO_COMPUTER}
        >
          <SelectTrigger className="h-9 w-56 rounded-md">
            <SelectValue placeholder={b.computerLoading} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NO_COMPUTER}>{b.computerNone}</SelectItem>
            {names.map(name => (
              <SelectItem key={name} value={name}>
                {name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button disabled={!current || open.isPending} onClick={() => open.mutate()} variant="secondary">
          {b.openComputer}
        </Button>
      </div>
    </section>
  )
}
