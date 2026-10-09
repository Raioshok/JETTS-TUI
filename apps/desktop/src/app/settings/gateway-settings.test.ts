import { describe, expect, it } from 'vitest'

import { normalizeSavedGatewayMode } from './gateway-settings'

describe('normalizeSavedGatewayMode', () => {
  it('opens a persisted cloud connection in the remote editor', () => {
    expect(normalizeSavedGatewayMode('cloud')).toBe('remote')
  })

  it('preserves supported connection modes', () => {
    expect(normalizeSavedGatewayMode('local')).toBe('local')
    expect(normalizeSavedGatewayMode('remote')).toBe('remote')
    expect(normalizeSavedGatewayMode('ssh')).toBe('ssh')
  })
})
