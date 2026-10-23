import { describe, expect, it } from 'vitest'

import { countLines, languageLabel } from './language-label'

describe('languageLabel', () => {
  it('maps known shiki ids to display names', () => {
    expect(languageLabel('typescript')).toBe('TypeScript')
    expect(languageLabel('JSON')).toBe('JSON')
  })

  it('falls back to a capitalized id, and to plain text when missing', () => {
    expect(languageLabel('elixir')).toBe('Elixir')
    expect(languageLabel(undefined)).toBe('Plain text')
    expect(languageLabel('')).toBe('Plain text')
  })
})

describe('countLines', () => {
  it('counts lines like an editor', () => {
    expect(countLines('')).toBe(0)
    expect(countLines('one')).toBe(1)
    expect(countLines('one\ntwo')).toBe(2)
    expect(countLines('one\ntwo\n')).toBe(2)
    expect(countLines('\n')).toBe(1)
  })
})
