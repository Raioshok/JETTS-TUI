import { describe, expect, it } from 'vitest'

import { formatUsd } from './format'

describe('formatUsd', () => {
  it('formats dollars for cost displays', () => {
    expect(formatUsd(0)).toBe('$0.00')
    expect(formatUsd(null)).toBe('$0.00')
    expect(formatUsd(0.004)).toBe('<$0.01')
    expect(formatUsd(12.345)).toBe('$12.35')
    expect(formatUsd(1234)).toBe('$1.2k')
  })
})
