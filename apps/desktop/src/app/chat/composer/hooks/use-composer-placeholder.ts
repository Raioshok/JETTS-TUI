import { useStore } from '@nanostores/react'
import { computed } from 'nanostores'
import { useEffect, useMemo, useRef, useState } from 'react'

import { useSessionView } from '@/app/chat/session-view'
import { useI18n } from '@/i18n'
import { $currentBotName, $newChatBot } from '@/store/bots'
import { resetBrowseState } from '@/store/composer-input-history'
import { $sessionStates } from '@/store/session-states'

import { pickPlaceholder } from '../composer-utils'

interface UseComposerPlaceholderOptions {
  disabled: boolean
  reconnecting: boolean
  sessionId: null | string | undefined
}

/**
 * The composer's placeholder text. A resting starter (new session) / continuation
 * (existing session) is picked once and only re-rolled when we genuinely move to
 * a *different* conversation — the null→id persist of a freshly-started session
 * keeps its starter so the text doesn't flip mid-stream. While the transport is
 * down, it swaps to a reconnecting / starting message instead.
 */
export function useComposerPlaceholder({ disabled, reconnecting, sessionId }: UseComposerPlaceholderOptions): string {
  const { t } = useI18n()
  const sessionView = useSessionView()
  const newChatBot = useStore($newChatBot)
  const currentBotName = useStore($currentBotName)

  const $tileBotName = useMemo(
    () => computed($sessionStates, states => (sessionId ? (states[sessionId]?.botName ?? '') : '')),
    [sessionId]
  )

  const tileBotName = useStore($tileBotName)

  // A Bot chat says who you're talking to; a fresh one before its session exists too.
  // Split tiles read their own slice's `botName` rather than primary-only globals.
  const botName = sessionView.kind === 'tile' ? tileBotName : sessionId ? currentBotName : newChatBot?.name || ''

  const newSessionPlaceholders = t.composer.newSessionPlaceholders
  const followUpPlaceholders = t.composer.followUpPlaceholders

  const [restingPlaceholder, setRestingPlaceholder] = useState(() =>
    pickPlaceholder(sessionId ? followUpPlaceholders : newSessionPlaceholders)
  )

  const prevSessionIdRef = useRef(sessionId)

  // eslint-disable-next-line no-restricted-syntax -- legitimate non-atom ref write (see eslint rule comment)
  useEffect(() => {
    const prev = prevSessionIdRef.current
    prevSessionIdRef.current = sessionId

    if (prev === sessionId) {
      return
    }

    // null → id: the new session we're already in just got persisted. Keep the
    // starter we showed instead of swapping to a follow-up under the user.
    if (prev == null && sessionId) {
      return
    }

    resetBrowseState(prev)
    setRestingPlaceholder(pickPlaceholder(sessionId ? followUpPlaceholders : newSessionPlaceholders))
  }, [followUpPlaceholders, newSessionPlaceholders, sessionId])

  // When the transport is disabled it's because the gateway isn't open.
  // Distinguish a cold start ("Starting JettsTUI...") from a dropped connection
  // we're trying to restore. During reconnect, keep the textbox editable so a
  // flaky network doesn't block drafting; only submit/backend actions stay
  // disabled until the gateway is open again.
  return disabled
    ? reconnecting
      ? t.composer.placeholderReconnecting
      : t.composer.placeholderStarting
    : botName
      ? t.composer.botPlaceholder(botName)
      : restingPlaceholder
}
