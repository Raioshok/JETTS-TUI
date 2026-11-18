import { act, renderHook } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { afterEach, describe, expect, it } from 'vitest'

import { PRIMARY_SESSION_VIEW, type SessionView, SessionViewProvider } from '@/app/chat/session-view'
import { createClientSessionState } from '@/lib/chat-runtime'
import { $currentBotName, $newChatBot } from '@/store/bots'
import { clearAllSessionStates, publishSessionState } from '@/store/session-states'

import { useComposerPlaceholder } from './use-composer-placeholder'

const resting = { disabled: false, reconnecting: false }

describe('useComposerPlaceholder with Jetts Bots', () => {
  afterEach(() => {
    $currentBotName.set('')
    $newChatBot.set(null)
    clearAllSessionStates()
  })

  it('names the Bot of the open chat, and nothing for an ordinary chat', () => {
    const { result } = renderHook(() => useComposerPlaceholder({ ...resting, sessionId: 's1' }))
    expect(result.current).not.toContain('Research')
    act(() => $currentBotName.set('Research'))
    expect(result.current).toBe('Message Research…')
  })

  it('names the Bot of a new chat before its session exists', () => {
    $newChatBot.set({ id: 'research', name: 'Research' })
    const { result } = renderHook(() => useComposerPlaceholder({ ...resting, sessionId: null }))
    expect(result.current).toBe('Message Research…')
  })

  it('does not leak primary bot globals into split session tiles', () => {
    $currentBotName.set('PrimaryBot')
    $newChatBot.set({ id: 'primary', name: 'PrimaryBot' })
    publishSessionState('tile-s1', createClientSessionState('stored-tile-1'))

    const tileView: SessionView = { ...PRIMARY_SESSION_VIEW, kind: 'tile' }

    const wrapper = ({ children }: { children: ReactNode }) =>
      createElement(SessionViewProvider, { value: tileView }, children)

    const { result } = renderHook(() => useComposerPlaceholder({ ...resting, sessionId: 'tile-s1' }), { wrapper })
    expect(result.current).not.toContain('PrimaryBot')
  })
})
