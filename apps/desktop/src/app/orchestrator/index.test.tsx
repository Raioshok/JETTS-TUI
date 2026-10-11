// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { $newChatRunAction } from '@/store/new-chat-run'
import { notifyError } from '@/store/notifications'
import { $flowPanelOpen } from '@/store/orchestrator-flow'
import { $gatewayState } from '@/store/session'

import type { OrchestratorConfig, OrchestratorPayload } from './flow-config'

const requestGateway = vi.fn()

vi.mock('../gateway/hooks/use-gateway-request', () => ({
  useGatewayRequest: () => ({ requestGateway })
}))

vi.mock('@/lib/model-options', () => ({
  requestModelOptions: () =>
    Promise.resolve({
      providers: [{ authenticated: true, models: ['claude-x', 'gemini-y'], name: 'Anthropic', slug: 'anthropic' }]
    })
}))

vi.mock('@/store/notifications', () => ({ notify: vi.fn(), notifyError: vi.fn() }))

const auto = { model: '', provider: '' }

function payload(config: OrchestratorConfig): OrchestratorPayload {
  const assignment = (role: 'executor' | 'planner' | 'reviewer' | 'verifier', model: string) => ({
    auto: !config.roles[role].model,
    model: config.roles[role].model || model,
    provider: 'anthropic',
    reason: 'best fit',
    role
  })

  return {
    assignments: {
      executor: assignment('executor', 'claude-x'),
      planner: assignment('planner', 'claude-x'),
      reviewer: assignment('reviewer', 'gemini-y'),
      verifier: assignment('verifier', 'gemini-y')
    },
    config
  }
}

const initial: OrchestratorConfig = {
  enabled: false,
  max_review_rounds: 2,
  roles: { executor: auto, planner: auto, reviewer: auto, verifier: auto }
}

async function renderView() {
  const { OrchestratorView } = await import('./index')
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

  await act(async () => {
    render(
      <QueryClientProvider client={client}>
        <OrchestratorView />
      </QueryClientProvider>
    )
  })
}

beforeEach(() => {
  $gatewayState.set('open')
  requestGateway.mockImplementation((method: string, params?: { config: OrchestratorConfig }) =>
    Promise.resolve(method === 'orchestrator.save' && params ? payload(params.config) : payload(initial))
  )
})

afterEach(() => {
  cleanup()
  requestGateway.mockReset()
  $newChatRunAction.set(null)
})

describe('OrchestratorView', () => {
  it('shows every role with the model Auto resolved to', async () => {
    await renderView()

    await waitFor(() => expect(screen.getByText('Planner')).toBeTruthy())
    expect(screen.getByText('Executor')).toBeTruthy()
    expect(screen.getByText('Reviewer')).toBeTruthy()
    expect(screen.getByText('Security & quality')).toBeTruthy()
    expect(screen.getAllByText('Auto → gemini-y')).toHaveLength(2)
  })

  it('saves the toggle and only runs once enabled, through the shell run action', async () => {
    const run = vi.fn()
    $newChatRunAction.set(run)
    await renderView()

    const runButton = await screen.findByRole('button', { name: 'Run in new chat' })
    fireEvent.change(screen.getByLabelText('Run a task'), { target: { value: 'add a dark mode toggle' } })
    expect((runButton as HTMLButtonElement).disabled).toBe(true)

    await act(async () => {
      fireEvent.click(screen.getByRole('switch'))
    })

    await waitFor(() =>
      expect(requestGateway).toHaveBeenCalledWith('orchestrator.save', {
        config: expect.objectContaining({ enabled: true })
      })
    )
    await waitFor(() => expect((runButton as HTMLButtonElement).disabled).toBe(false))

    fireEvent.click(runButton)
    expect(run).toHaveBeenCalledTimes(1)
    expect(run.mock.calls[0][0]).toContain('orchestrate tool')
    expect(run.mock.calls[0][0]).toContain('add a dark mode toggle')
  })

  it('saves the Auto cost/quality balance', async () => {
    await renderView()

    const economy = await screen.findByRole('button', { name: 'Economy' })
    expect(screen.getByRole('button', { name: 'Balanced' }).getAttribute('aria-pressed')).toBe('true')

    await act(async () => {
      fireEvent.click(economy)
    })

    await waitFor(() =>
      expect(requestGateway).toHaveBeenCalledWith('orchestrator.save', {
        config: expect.objectContaining({ auto_balance: 'economy' })
      })
    )
    expect(economy.getAttribute('aria-pressed')).toBe('true')
  })

  it('opens the flow sidebar on request', async () => {
    $flowPanelOpen.set(false)
    await renderView()

    fireEvent.click(await screen.findByRole('button', { name: 'Show flow sidebar' }))
    expect($flowPanelOpen.get()).toBe(true)
  })

  it('rolls the choice back when the save fails', async () => {
    requestGateway.mockImplementation((method: string) =>
      method === 'orchestrator.save' ? Promise.reject(new Error('disk full')) : Promise.resolve(payload(initial))
    )
    await renderView()

    const toggle = await screen.findByRole('switch')

    await act(async () => {
      fireEvent.click(toggle)
    })

    await waitFor(() =>
      expect(notifyError).toHaveBeenCalledWith(expect.any(Error), 'Could not save the orchestrator settings')
    )
    expect(toggle.getAttribute('aria-checked')).toBe('false')
  })
})
