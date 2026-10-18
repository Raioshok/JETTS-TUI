import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

const request = vi.fn()

vi.mock('@/store/gateway', () => ({ activeGateway: () => ({ request }) }))
vi.mock('@/i18n', () => ({
  useI18n: () => ({
    t: {
      common: { close: 'Close' },
      sidebar: {
        usage: {
          title: 'Session usage',
          loading: 'Loading…',
          unavailable: 'Usage unavailable for this session.',
          workingTime: 'Working time',
          estCost: 'Est. cost',
          included: 'Included',
          costUnknown: '—',
          model: 'Model',
          apiCalls: 'API calls',
          toolCalls: 'Tool calls',
          tokensIn: 'Tokens in',
          tokensOut: 'Tokens out',
          tokensCached: 'Tokens cached'
        }
      }
    }
  })
}))

import { SessionUsageDialog } from './session-usage-dialog'

const baseStats = {
  session_id: 's1',
  model: 'gpt-5.6-sol',
  provider: 'openai',
  active_seconds: 125,
  wall_seconds: 4000,
  api_call_count: 12,
  tool_call_count: 7,
  input_tokens: 3400,
  output_tokens: 1200,
  cache_read_tokens: 50000,
  cache_write_tokens: 0,
  reasoning_tokens: 0,
  total_tokens: 54600,
  cost_usd: 0.1234,
  cost_status: 'estimated',
  cost_label: 'est'
}

afterEach(() => {
  request.mockReset()
})

describe('SessionUsageDialog', () => {
  it('shows working time, cost and token breakdown from session.stats', async () => {
    request.mockResolvedValue(baseStats)
    render(<SessionUsageDialog onOpenChange={() => {}} open sessionId="s1" title="My chat" />)

    await waitFor(() => expect(screen.getByText('2m 5s')).toBeTruthy())
    expect(request).toHaveBeenCalledWith('session.stats', { session_id: 's1' })
    expect(screen.getByText('$0.123')).toBeTruthy()
    expect(screen.getByText('gpt-5.6-sol')).toBeTruthy()
    expect(screen.getByText('50K')).toBeTruthy()
  })

  it('renders a subscription provider with no price as Included', async () => {
    request.mockResolvedValue({ ...baseStats, provider: 'antigravity', cost_usd: 0, cost_status: 'unknown' })
    render(<SessionUsageDialog onOpenChange={() => {}} open sessionId="s1" />)

    await waitFor(() => expect(screen.getByText('Included')).toBeTruthy())
  })

  it('shows an unavailable message when the RPC fails', async () => {
    request.mockRejectedValue(new Error('nope'))
    render(<SessionUsageDialog onOpenChange={() => {}} open sessionId="s1" />)

    await waitFor(() => expect(screen.getByText('Usage unavailable for this session.')).toBeTruthy())
  })
})
