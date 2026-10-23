import { describe, expect, it } from 'vitest'

import { sessionDotState, sessionPreviewLine, sessionShowsRunningArc } from './session-row-state'

describe('session row running appearance', () => {
  it('keeps the running arc when an authoritative turn becomes quiet', () => {
    expect(sessionShowsRunningArc({ isWorking: true, needsInput: false })).toBe(true)
    expect(
      sessionDotState({
        hasBackground: false,
        isStalled: true,
        isUnread: false,
        isWorking: true,
        needsInput: false
      })
    ).toBe('stalled')
  })

  it('uses the needs-input treatment instead of the running arc', () => {
    expect(sessionShowsRunningArc({ isWorking: true, needsInput: true })).toBe(false)
    expect(
      sessionDotState({
        hasBackground: true,
        isStalled: true,
        isUnread: true,
        isWorking: true,
        needsInput: true
      })
    ).toBe('needs-input')
  })

  it('keeps background and unread states below active-turn states', () => {
    expect(
      sessionDotState({
        hasBackground: true,
        isStalled: false,
        isUnread: true,
        isWorking: false,
        needsInput: false
      })
    ).toBe('background')
  })
})

describe('sessionPreviewLine', () => {
  it('shows a preview that adds information beyond the title', () => {
    expect(sessionPreviewLine('Comparing transformer variants for seq2seq', 'Neural architecture analysis')).toBe(
      'Comparing transformer variants for seq2seq'
    )
  })

  it('hides a preview that only repeats (or is repeated by) the title', () => {
    expect(sessionPreviewLine('Plan the onboarding flow for new users', 'Plan the onboarding flow')).toBeNull()
    expect(sessionPreviewLine('Plan the onboarding', 'Plan the onboarding flow…')).toBeNull()
    expect(sessionPreviewLine('  plan THE  onboarding flow ', 'Plan the onboarding flow')).toBeNull()
  })

  it('hides empty previews and collapses whitespace in kept ones', () => {
    expect(sessionPreviewLine(undefined, 'Title')).toBeNull()
    expect(sessionPreviewLine('   ', 'Title')).toBeNull()
    expect(sessionPreviewLine('line one\n  line two', 'Title')).toBe('line one line two')
  })
})
