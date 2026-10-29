import { useStore } from '@nanostores/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { PageLoader } from '@/components/page-loader'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from '@/components/ui/dialog'
import { ErrorState } from '@/components/ui/error-state'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { useI18n } from '@/i18n'
import { $newChatBot, botsNeedingNotice, type JettsBot } from '@/store/bots'
import { notify, notifyError } from '@/store/notifications'
import { $activeGatewayProfile, normalizeProfileKey } from '@/store/profile'
import { $gatewayState } from '@/store/session'

import { useGatewayRequest } from '../gateway/hooks/use-gateway-request'
import { openSession } from '../open-session'
import { NEW_CHAT_ROUTE } from '../routes'

export function BotsView(props: React.ComponentProps<'section'>) {
  const { t } = useI18n()
  const b = t.bots
  const navigate = useNavigate()
  const { requestGateway } = useGatewayRequest()
  const queryClient = useQueryClient()
  const gatewayState = useStore($gatewayState)
  const profile = normalizeProfileKey(useStore($activeGatewayProfile))
  const scope = { profile }
  const queryKey = ['bots', profile] as const

  const [createOpen, setCreateOpen] = useState(false)
  const [name, setName] = useState('')
  const [role, setRole] = useState('')
  const [pendingRemove, setPendingRemove] = useState<JettsBot | null>(null)
  const [taskFor, setTaskFor] = useState<JettsBot | null>(null)
  const [task, setTask] = useState('')

  const bots = useQuery({
    queryKey,
    queryFn: async () => {
      const next = await requestGateway<{ bots: JettsBot[] }>('bots.list', scope)
      // Compare with the cached list so only real transitions notify; the
      // first load has nothing cached and stays quiet.
      const previous = queryClient.getQueryData<{ bots: JettsBot[] }>(queryKey)

      if (previous) {
        const seen = new Map(previous.bots.map(bot => [bot.id, bot.status ?? 'idle']))

        for (const { bot, status } of botsNeedingNotice(seen, next.bots)) {
          notify({
            kind: status === 'needs_you' ? 'warning' : 'success',
            title: bot.name,
            message: status === 'needs_you' ? b.needsYou(bot.name) : b.finished(bot.name),
            action: { label: b.open, onClick: () => openBot(bot) }
          })
        }
      }

      return next
    },
    enabled: gatewayState === 'open',
    // Poll only while a bot is busy; idle rosters stay quiet.
    refetchInterval: query => (query.state.data?.bots.some(bot => (bot.status ?? 'idle') !== 'idle') ? 3000 : false)
  })

  const assign = useMutation({
    mutationFn: (bot: JettsBot) => requestGateway('bots.assign', { ...scope, id: bot.id, task }),
    onError: error => notifyError(error, b.assignFailed),
    onSuccess: (_result, bot) => {
      notify({ kind: 'info', title: bot.name, message: b.assigned(bot.name) })
      // Optimistic: a task that finishes before the next poll still notifies.
      queryClient.setQueryData<{ bots: JettsBot[] }>(queryKey, current =>
        current
          ? { bots: current.bots.map(item => (item.id === bot.id ? { ...item, status: 'working' } : item)) }
          : current
      )
      setTaskFor(null)
      setTask('')
      void queryClient.invalidateQueries({ queryKey })
    }
  })

  const create = useMutation({
    mutationFn: () => requestGateway<{ bot: JettsBot }>('bots.create', { ...scope, name, role }),
    onError: error => notifyError(error, b.createFailed),
    onSuccess: () => {
      setCreateOpen(false)
      setName('')
      setRole('')
      void queryClient.invalidateQueries({ queryKey })
    }
  })

  const openBot = (bot: JettsBot) => {
    if (bot.session_id) {
      openSession(bot.session_id, navigate)

      return
    }

    // First chat: the next message creates the session as this bot's thread.
    $newChatBot.set(bot.id)
    navigate(NEW_CHAT_ROUTE)
  }

  const list = bots.data?.bots

  const remove = async () => {
    if (!pendingRemove) {
      return
    }

    await requestGateway('bots.remove', { ...scope, id: pendingRemove.id })
    await queryClient.invalidateQueries({ queryKey })
  }

  if (bots.isError) {
    return (
      <section {...props} className="grid h-full place-items-center bg-(--ui-chat-surface-background) px-6">
        <ErrorState description={String(bots.error)} title={b.loadFailed}>
          <Button onClick={() => void bots.refetch()} variant="secondary">
            {b.retry}
          </Button>
        </ErrorState>
      </section>
    )
  }

  if (!list) {
    return <PageLoader />
  }

  return (
    <section
      {...props}
      className="flex h-full min-w-0 flex-col overflow-hidden bg-(--ui-chat-surface-background)"
      data-testid="bots-view"
    >
      <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
        <div className="mx-auto grid w-full max-w-4xl gap-6 px-4 pb-8 pt-[calc(var(--titlebar-height,34px)+0.75rem)] sm:px-6">
          <header className="flex flex-wrap items-end justify-between gap-4">
            <div className="grid max-w-2xl gap-1">
              <h1 className="text-xl font-semibold tracking-tight text-(--ui-text-primary)">{b.title}</h1>
              <p className="text-sm leading-5 text-(--ui-text-secondary)">{b.subtitle}</p>
            </div>
            <Button onClick={() => setCreateOpen(true)}>{b.newBot}</Button>
          </header>

          {list.length === 0 ? (
            <p className="text-sm text-(--ui-text-secondary)">{b.empty}</p>
          ) : (
            <ul className="divide-y divide-(--ui-stroke-tertiary)">
              {list.map(bot => (
                <li className="flex items-start justify-between gap-4 py-3" key={bot.id}>
                  <div className="grid min-w-0 gap-1">
                    <span className="flex items-center gap-2 text-sm font-medium text-(--ui-text-primary)">
                      {bot.name}
                      {bot.status && bot.status !== 'idle' && (
                        <span className="rounded-full bg-foreground/5 px-2 py-0.5 text-xs font-normal text-(--ui-text-secondary)">
                          {b.status[bot.status]}
                        </span>
                      )}
                    </span>
                    <span className="line-clamp-2 text-sm text-(--ui-text-secondary)">{bot.role}</span>
                    {bot.model && <span className="text-xs text-(--ui-text-tertiary)">{bot.model}</span>}
                  </div>
                  <div className="flex shrink-0 gap-2">
                    <Button onClick={() => setTaskFor(bot)} size="sm" variant="secondary">
                      {b.giveTask}
                    </Button>
                    <Button onClick={() => openBot(bot)} size="sm">
                      {bot.session_id ? b.open : b.start}
                    </Button>
                    <Button onClick={() => setPendingRemove(bot)} size="sm" variant="ghost">
                      {b.remove}
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <Dialog onOpenChange={setCreateOpen} open={createOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{b.newBot}</DialogTitle>
            <DialogDescription>{b.createHint}</DialogDescription>
          </DialogHeader>
          <form
            className="grid gap-4"
            onSubmit={event => {
              event.preventDefault()
              create.mutate()
            }}
          >
            <Field label={b.nameLabel}>
              <Input
                autoFocus
                onChange={event => setName(event.target.value)}
                placeholder={b.namePlaceholder}
                value={name}
              />
            </Field>
            <Field label={b.roleLabel}>
              <Textarea
                onChange={event => setRole(event.target.value)}
                placeholder={b.rolePlaceholder}
                rows={4}
                value={role}
              />
            </Field>
            <DialogFooter>
              <Button disabled={!name.trim() || !role.trim() || create.isPending} type="submit">
                {b.create}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog onOpenChange={open => !open && setTaskFor(null)} open={taskFor !== null}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{taskFor ? b.giveTaskTitle(taskFor.name) : b.giveTask}</DialogTitle>
            <DialogDescription>{b.giveTaskHint}</DialogDescription>
          </DialogHeader>
          <form
            className="grid gap-4"
            onSubmit={event => {
              event.preventDefault()

              if (taskFor) {
                assign.mutate(taskFor)
              }
            }}
          >
            <Textarea
              autoFocus
              onChange={event => setTask(event.target.value)}
              placeholder={b.taskPlaceholder}
              rows={5}
              value={task}
            />
            <DialogFooter>
              <Button disabled={!task.trim() || assign.isPending} type="submit">
                {b.assign}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        confirmLabel={b.remove}
        description={pendingRemove ? b.removeHint(pendingRemove.name) : ''}
        destructive
        onClose={() => setPendingRemove(null)}
        onConfirm={remove}
        open={pendingRemove !== null}
        title={b.removeTitle}
      />
    </section>
  )
}
