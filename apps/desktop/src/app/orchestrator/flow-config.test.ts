import { describe, expect, it } from 'vitest'

import {
  AUTO_CHOICE,
  balanceOf,
  DEFAULT_BALANCE,
  MAX_REVIEW_ROUNDS,
  orchestratePrompt,
  type OrchestratorConfig,
  parseRoleChoice,
  roleChoice,
  withBalance,
  withReviewRounds,
  withRoleChoice
} from './flow-config'

const base: OrchestratorConfig = {
  enabled: true,
  max_review_rounds: 2,
  roles: {
    planner: { provider: '', model: '' },
    executor: { provider: '', model: '' },
    reviewer: { provider: '', model: '' },
    verifier: { provider: '', model: '' }
  }
}

describe('orchestrator role choices', () => {
  it('round-trips provider:model, including models that contain a colon', () => {
    for (const role of [
      { provider: 'anthropic', model: 'claude-sonnet' },
      { provider: 'openrouter', model: 'anthropic/claude-sonnet-4:beta' }
    ]) {
      expect(parseRoleChoice(roleChoice(role))).toEqual(role)
    }
  })

  it('treats an unpinned role as Auto and Auto as unpinned', () => {
    expect(roleChoice({ provider: 'x', model: '' })).toBe(AUTO_CHOICE)
    expect(parseRoleChoice(AUTO_CHOICE)).toEqual({ provider: '', model: '' })
  })

  it('changes only the targeted role', () => {
    const next = withRoleChoice(base, 'reviewer', 'gemini:gemini-pro')

    expect(next.roles.reviewer).toEqual({ provider: 'gemini', model: 'gemini-pro' })
    expect(next.roles.executor).toBe(base.roles.executor)
    expect(base.roles.reviewer.model).toBe('')
  })

  it('clamps review rounds to the backend range', () => {
    expect(withReviewRounds(base, -3).max_review_rounds).toBe(0)
    expect(withReviewRounds(base, 99).max_review_rounds).toBe(MAX_REVIEW_ROUNDS)
  })

  it('names the orchestrate tool and carries the task', () => {
    const prompt = orchestratePrompt('  add dark mode  ')

    expect(prompt).toContain('orchestrate tool')
    expect(prompt.endsWith('add dark mode')).toBe(true)
  })
})

describe('orchestrator auto balance', () => {
  it('defaults configs saved before the setting existed, and round-trips a choice', () => {
    expect(balanceOf(base)).toBe(DEFAULT_BALANCE)
    expect(balanceOf(withBalance(base, 'economy'))).toBe('economy')
    expect(balanceOf({ ...base, auto_balance: 'bogus' as never })).toBe(DEFAULT_BALANCE)
  })

  it('leaves the rest of the config untouched', () => {
    const next = withBalance(base, 'quality')
    expect({ ...next, auto_balance: undefined }).toEqual({ ...base, auto_balance: undefined })
  })
})
