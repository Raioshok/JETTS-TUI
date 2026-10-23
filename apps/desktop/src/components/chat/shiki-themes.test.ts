import { describe, expect, it } from 'vitest'

import { IVORY_SYNTAX, skinSyntaxTheme } from './shiki-themes'

describe('skinSyntaxTheme', () => {
  it('returns the skin pair for a skin that ships one', () => {
    expect(skinSyntaxTheme('ivory')).toBe(IVORY_SYNTAX)
  })

  it('returns undefined so other skins keep the caller default', () => {
    expect(skinSyntaxTheme('jettstui')).toBeUndefined()
    expect(skinSyntaxTheme('nope')).toBeUndefined()
  })

  it('ships matching light/dark variants with distinct names', () => {
    const pair = skinSyntaxTheme('ivory')!
    expect(pair.light.type).toBe('light')
    expect(pair.dark.type).toBe('dark')
    expect(pair.light.name).not.toBe(pair.dark.name)
  })
})
