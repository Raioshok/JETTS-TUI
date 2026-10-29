import { describe, expect, it } from 'vitest'

import { botsNeedingNotice, type JettsBot, type JettsBotStatus } from './bots'

const bot = (id: string, status?: JettsBotStatus): JettsBot => ({ id, name: id, role: 'job', status })

describe('botsNeedingNotice', () => {
  it('announces a finished task and a new approval request, once each', () => {
    const before = new Map<string, JettsBotStatus>([
      ['done', 'working'],
      ['asks', 'working'],
      ['still', 'working'],
      ['quiet', 'idle']
    ])

    const notices = botsNeedingNotice(before, [
      bot('done', 'idle'),
      bot('asks', 'needs_you'),
      bot('still', 'working'),
      bot('quiet')
    ])

    expect(notices.map(n => [n.bot.id, n.status])).toEqual([
      ['done', 'idle'],
      ['asks', 'needs_you']
    ])
    expect(botsNeedingNotice(new Map([['asks', 'needs_you']]), [bot('asks', 'needs_you')])).toEqual([])
  })

  it('treats an approved request that finished as finished, and ignores bots seen for the first time', () => {
    expect(botsNeedingNotice(new Map([['b', 'needs_you']]), [bot('b', 'idle')]).map(n => n.status)).toEqual(['idle'])
    expect(botsNeedingNotice(new Map(), [bot('new', 'idle')])).toEqual([])
  })
})
