import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { $currentBotName, $newChatBot } from '@/store/bots'

import { useComposerPlaceholder } from './use-composer-placeholder'

const resting = { disabled: false, reconnecting: false }

describe('useComposerPlaceholder with Jetts Bots', () => {
  afterEach(() => {
    $currentBotName.set('')
    $newChatBot.set(null)
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
})
