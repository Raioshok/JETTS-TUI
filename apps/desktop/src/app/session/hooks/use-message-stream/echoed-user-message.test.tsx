import { QueryClient } from '@tanstack/react-query'
import { act, cleanup, render, waitFor } from '@testing-library/react'
import { useEffect, useRef } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ClientSessionState } from '@/app/types'
import { chatMessageText } from '@/lib/chat-messages'
import { createClientSessionState } from '@/lib/chat-runtime'
import type { RpcEvent } from '@/types/jettstui'

import { useMessageStream } from './index'

const SID = 'session-1'

let handleEvent: ((event: RpcEvent) => void) | null = null
let sessionStates: Map<string, ClientSessionState>

function Harness() {
  const activeSessionIdRef = useRef<string | null>(SID)
  const sessionStateByRuntimeIdRef = useRef(new Map<string, ClientSessionState>())
  const queryClientRef = useRef(new QueryClient())

  const stream = useMessageStream({
    activeSessionIdRef,
    hydrateFromStoredSession: vi.fn(async () => undefined),
    queryClient: queryClientRef.current,
    refreshJettsTUIConfig: vi.fn(async () => undefined),
    refreshSessions: vi.fn(async () => undefined),
    sessionStateByRuntimeIdRef,
    updateSessionState: (sessionId, updater) => {
      const current = sessionStateByRuntimeIdRef.current.get(sessionId) ?? createClientSessionState()
      const next = updater(current)
      sessionStateByRuntimeIdRef.current.set(sessionId, next)
      sessionStates.set(sessionId, next)

      return next
    }
  })

  useEffect(() => {
    handleEvent = stream.handleGatewayEvent
  }, [stream.handleGatewayEvent])

  return null
}

const send = (type: string, payload: Record<string, unknown> = {}) =>
  act(() => handleEvent!({ payload, session_id: SID, type }))

const transcript = () =>
  (sessionStates.get(SID) ?? createClientSessionState()).messages
    .filter(m => !m.hidden)
    .map(m => `${m.role}: ${chatMessageText(m)}`)

describe('backend-sent user messages', () => {
  afterEach(() => {
    cleanup()
    handleEvent = null
  })

  it('shows a task the backend sent before the reply to it', async () => {
    sessionStates = new Map()
    render(<Harness />)
    await waitFor(() => expect(handleEvent).not.toBeNull())

    await send('message.start', { user_text: 'What is the tallest mountain in Africa?' })
    await send('message.delta', { text: 'Kilimanjaro.' })
    await send('message.complete', { text: 'Kilimanjaro.' })

    expect(transcript()).toEqual(['user: What is the tallest mountain in Africa?', 'assistant: Kilimanjaro.'])
  })

  it('adds nothing for an ordinary turn, whose message the client drew itself', async () => {
    sessionStates = new Map()
    render(<Harness />)
    await waitFor(() => expect(handleEvent).not.toBeNull())

    await send('message.start')
    await send('message.complete', { text: 'Hi.' })

    expect(transcript()).toEqual(['assistant: Hi.'])
  })
})
