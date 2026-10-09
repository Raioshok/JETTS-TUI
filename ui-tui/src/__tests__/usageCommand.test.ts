import { beforeEach, describe, expect, it, vi } from 'vitest'

import { sessionCommands } from '../app/slash/commands/session.js'
import type { SessionUsageResponse } from '../gatewayTypes.js'

const usageCommand = sessionCommands.find(cmd => cmd.name === 'usage')!

const guarded =
  <T>(fn: (r: T) => void) =>
  (r: null | T) => {
    if (r) {
      fn(r)
    }
  }

/** Build a ctx whose rpc routes by method name to a supplied map of results. */
const buildCtx = (results: Record<string, unknown>) => {
  const sys = vi.fn()
  const panel = vi.fn()

  const rpc = vi.fn((method: string, _params: unknown) => Promise.resolve(results[method]))

  const ctx = {
    gateway: { rpc },
    guarded,
    guardedErr: vi.fn(),
    sid: 'sid-1',
    stale: () => false,
    transcript: { page: vi.fn(), panel, sys }
  }

  const run = async (arg: string) => {
    usageCommand.run(arg, ctx as any, 'usage')
    await rpc.mock.results[0]?.value
    await Promise.resolve()
    await Promise.resolve()
  }

  return { ctx, panel, run, sys }
}

const baseUsage = (overrides: Partial<SessionUsageResponse> = {}): SessionUsageResponse =>
  ({ calls: 0, input: 0, output: 0, total: 0, ...overrides }) as SessionUsageResponse

const printed = (sys: ReturnType<typeof vi.fn>) => sys.mock.calls.map(c => c[0]).join('\n')

describe('/usage slash command', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('reports an empty session without advertising a removed billing flow', async () => {
    const empty = buildCtx({ 'session.usage': baseUsage({ calls: 0, credits_lines: [] }) })
    await empty.run('')
    expect(printed(empty.sys)).toContain('no API calls yet')
    expect(printed(empty.sys)).not.toContain('/topup')
    expect(empty.panel).not.toHaveBeenCalled()
  })

  it('shows token and context usage without rendering a Portal balance', async () => {
    const { panel, run } = buildCtx({
      'session.usage': baseUsage({
        calls: 2,
        input: 100,
        output: 50,
        total: 150,
        context_max: 1000,
        context_used: 200,
        context_percent: 20,
        usage: { available: true, status: 'healthy', plan_name: 'Plus' }
      })
    })

    await run('')
    expect(panel).toHaveBeenCalledWith('Usage', expect.any(Array))
    expect(JSON.stringify(panel.mock.calls)).toContain('Input tokens')
    expect(JSON.stringify(panel.mock.calls)).toContain('Context: 200 / 1,000 (20%)')
    expect(JSON.stringify(panel.mock.calls)).not.toContain('Plus')
  })

  it('does not upsell subscriptions from an empty free account', async () => {
    const { panel, run, sys } = buildCtx({
      'session.usage': baseUsage({ usage: { available: true, status: 'free', plan_name: null } })
    })

    await run('')
    expect(panel).not.toHaveBeenCalled()
    expect(printed(sys)).toBe('no API calls yet')
  })
})
