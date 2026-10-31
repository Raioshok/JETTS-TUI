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
import { Field, FieldHint } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { useI18n } from '@/i18n'
import type { JettsBot } from '@/store/bots'
import { notifyError } from '@/store/notifications'

import { useGatewayRequest } from '../gateway/hooks/use-gateway-request'

interface EditBotButtonProps {
  bot: JettsBot
  onChanged: () => void
  profile: string
}

/** Edit a Bot's job and its enforced limits (which tools, which need your OK). */
export function EditBotButton({ bot, onChanged, profile }: EditBotButtonProps) {
  const { t } = useI18n()
  const b = t.bots
  const { requestGateway } = useGatewayRequest()
  const [open, setOpen] = useState(false)
  const [role, setRole] = useState(bot.role)
  const [tools, setTools] = useState((bot.tools ?? []).join(', '))
  const [askBefore, setAskBefore] = useState((bot.ask_before ?? []).join(', '))

  const save = useMutation({
    mutationFn: () => requestGateway('bots.update', { profile, id: bot.id, role, tools, ask_before: askBefore }),
    onError: error => notifyError(error, b.saveFailed),
    onSuccess: () => {
      setOpen(false)
      onChanged()
    }
  })

  const openDialog = () => {
    setRole(bot.role)
    setTools((bot.tools ?? []).join(', '))
    setAskBefore((bot.ask_before ?? []).join(', '))
    setOpen(true)
  }

  return (
    <>
      <Button onClick={openDialog} size="sm" variant="ghost">
        {b.edit}
      </Button>
      <Dialog onOpenChange={setOpen} open={open}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{b.editTitle(bot.name)}</DialogTitle>
            <DialogDescription>{b.editHint}</DialogDescription>
          </DialogHeader>
          <form
            className="grid gap-4"
            onSubmit={event => {
              event.preventDefault()
              save.mutate()
            }}
          >
            <Field label={b.roleLabel}>
              <Textarea onChange={event => setRole(event.target.value)} rows={3} value={role} />
            </Field>
            <Field label={b.toolsLabel} optional>
              <Input
                onChange={event => setTools(event.target.value)}
                placeholder="web_search, browser_navigate"
                value={tools}
              />
              <FieldHint>{b.toolsHint}</FieldHint>
            </Field>
            <Field label={b.askLabel} optional>
              <Input
                onChange={event => setAskBefore(event.target.value)}
                placeholder="send_message"
                value={askBefore}
              />
              <FieldHint>{b.askHint}</FieldHint>
            </Field>
            <DialogFooter>
              <Button disabled={!role.trim() || save.isPending} type="submit">
                {b.save}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  )
}
