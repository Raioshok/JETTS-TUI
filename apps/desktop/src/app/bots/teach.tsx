import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from '@/components/ui/dialog'
import { Field } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { useI18n } from '@/i18n'
import type { JettsBot } from '@/store/bots'
import { notify, notifyError } from '@/store/notifications'

import { useGatewayRequest } from '../gateway/hooks/use-gateway-request'

interface TeachButtonProps {
  bot: JettsBot
  /** Refresh the roster after a lesson starts or ends. */
  onChanged: () => void
  profile: string
}

/** Teach a Bot by showing it once: start watching, then stop and let it learn. */
export function TeachButton({ bot, onChanged, profile }: TeachButtonProps) {
  const { t } = useI18n()
  const b = t.bots
  const { requestGateway } = useGatewayRequest()
  const [dialog, setDialog] = useState<'start' | 'stop' | null>(null)
  const [title, setTitle] = useState('')
  const [notes, setNotes] = useState('')

  const start = useMutation({
    mutationFn: () => requestGateway<{ source: string }>('bots.teach_start', { profile, id: bot.id, title }),
    onError: error => notifyError(error, b.teachStartFailed),
    onSuccess: ({ source }) => {
      notify({ kind: 'info', title: bot.name, message: b.teachWatching(bot.name, source) })
      setDialog(null)
      setTitle('')
      onChanged()
    }
  })

  const stop = useMutation({
    mutationFn: () => requestGateway<{ frames: number }>('bots.teach_stop', { profile, id: bot.id, notes }),
    onError: error => {
      notifyError(error, b.learnFailed)
      onChanged()
    },
    onSuccess: ({ frames }) => {
      notify({ kind: 'info', title: bot.name, message: b.learning(bot.name, frames) })
      setDialog(null)
      setNotes('')
      onChanged()
    }
  })

  return (
    <>
      {bot.watching ? (
        <Button onClick={() => setDialog('stop')} size="sm">
          {b.stopLearn}
        </Button>
      ) : (
        <Button onClick={() => setDialog('start')} size="sm" variant="ghost">
          {b.teach}
        </Button>
      )}

      <Dialog onOpenChange={open => !open && setDialog(null)} open={dialog === 'start'}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{b.teachTitle(bot.name)}</DialogTitle>
            <DialogDescription>{b.teachHint}</DialogDescription>
          </DialogHeader>
          <form
            className="grid gap-4"
            onSubmit={event => {
              event.preventDefault()
              start.mutate()
            }}
          >
            <Field label={b.teachWhatLabel}>
              <Input
                autoFocus
                onChange={event => setTitle(event.target.value)}
                placeholder={b.teachWhatPlaceholder}
                value={title}
              />
            </Field>
            <DialogFooter>
              <Button disabled={!title.trim() || start.isPending} type="submit">
                {b.teachStart}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog onOpenChange={open => !open && setDialog(null)} open={dialog === 'stop'}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{b.stopTitle(bot.name)}</DialogTitle>
            <DialogDescription>{b.stopHint}</DialogDescription>
          </DialogHeader>
          <form
            className="grid gap-4"
            onSubmit={event => {
              event.preventDefault()
              stop.mutate()
            }}
          >
            <Field label={b.notesLabel} optional>
              <Textarea
                autoFocus
                onChange={event => setNotes(event.target.value)}
                placeholder={b.notesPlaceholder}
                rows={3}
                value={notes}
              />
            </Field>
            <DialogFooter>
              <Button disabled={stop.isPending} type="submit">
                {b.stopLearn}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  )
}
