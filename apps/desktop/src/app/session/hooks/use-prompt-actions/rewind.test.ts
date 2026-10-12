import { describe, expect, it } from 'vitest'

import type { ChatMessage } from '@/lib/chat-messages'

import {
  trimLastExchange,
  truncateSubmitParams
} from './rewind'

describe('truncateSubmitParams', () => {
  it('omits truncation fields when no ordinal is set', () => {
    expect(truncateSubmitParams(undefined)).toEqual({})
  })

  it('requires confirm_empty_truncate only for ordinal 0', () => {
    expect(truncateSubmitParams(0)).toEqual({
      truncate_before_user_ordinal: 0,
      confirm_empty_truncate: true
    })
    expect(truncateSubmitParams(1)).toEqual({
      truncate_before_user_ordinal: 1
    })
  })
})

describe('trimLastExchange (/retry)', () => {
  const msg = (id: string, role: ChatMessage['role'], hidden = false): ChatMessage =>
    ({ id, role, parts: [], hidden }) as unknown as ChatMessage

  it('drops the last visible user turn and everything after it', () => {
    const messages = [msg('u1', 'user'), msg('a1', 'assistant'), msg('u2', 'user'), msg('a2', 'assistant')]

    expect(trimLastExchange(messages).map(m => m.id)).toEqual(['u1', 'a1'])
  })

  it('skips hidden user rows and leaves a user-less transcript alone', () => {
    const messages = [msg('u1', 'user'), msg('a1', 'assistant'), msg('h', 'user', true)]

    expect(trimLastExchange(messages).map(m => m.id)).toEqual([])
    expect(trimLastExchange([msg('s', 'system')]).map(m => m.id)).toEqual(['s'])
  })
})

