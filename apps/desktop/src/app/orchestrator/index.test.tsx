// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { notifyError } from '@/store/notifications'
import { $activeSessionId, $currentCwd, $gatewayState } from '@/store/session'

import type { OrchestratorConfig, OrchestratorPayload } from './flow-config'
import type { HeadlessRun } from './headless-runs'

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

/** Settings live on the Team & models tab; Runs is the default. */
async function renderTeamTab() {
  await renderView()
  fireEvent.click(await screen.findByRole('button', { name: 'Team & models' }))
}

const CWD = '/work/app'
let runs: HeadlessRun[] = []

function headlessRun(overrides: Partial<HeadlessRun> = {}): HeadlessRun {
  return {
    cwd: CWD,
    error: '',
    events: [
      {
        at: 1000,
        type: 'orchestrator.run',
        payload: {
          run_id: 'flow-1',
          status: 'running',
          task: 'add a dark mode toggle',
          round: 1,
          max_rounds: 3,
          phase: 'work'
        }
      },
      {
        at: 1001,
        type: 'orchestrator.stage',
        payload: {
          run_id: 'flow-1',
          role: 'executor',
          phase: 'work',
          round: 1,
          status: 'running',
          subagent_id: 'sa-1',
          model: 'claude-x'
        }
      }
    ],
    finished_at: null,
    id: 'orch_1',
    note: '',
    started_at: 1000,
    status: 'running',
    subagents: [
      {
        current_tool: 'write_file',
        id: 'sa-1',
        model: 'claude-x',
        status: 'running',
        stream: [{ at: 1002, error: false, text: 'write_file src/theme.ts' }]
      }
    ],
    task: 'add a dark mode toggle',
    verdict: '',
    ...overrides
  }
}

beforeEach(() => {
  $gatewayState.set('open')
  $currentCwd.set(CWD)
  $activeSessionId.set('sess-3')
  runs = []
  requestGateway.mockImplementation((method: string, params?: { config: OrchestratorConfig }) => {
    switch (method) {
      case 'orchestrator.save':
        return Promise.resolve(payload(params!.config))

      case 'orchestrator.runs':
        return Promise.resolve({ runs })

      case 'orchestrator.run':
        return Promise.resolve({ run: headlessRun() })

      case 'orchestrator.stop':
        return Promise.resolve({ stopped: true })

      default:
        return Promise.resolve(payload(initial))
    }
  })
})

afterEach(() => {
  cleanup()
  requestGateway.mockReset()
  vi.mocked(notifyError).mockReset()
  $activeSessionId.set(null)
})

describe('Orchestrator team settings', () => {
  it('shows every role with the model Auto resolved to', async () => {
    await renderTeamTab()

    await waitFor(() => expect(screen.getByText('Planner')).toBeTruthy())
    expect(screen.getByText('Executor')).toBeTruthy()
    expect(screen.getByText('Reviewer')).toBeTruthy()
    expect(screen.getByText('Security & quality')).toBeTruthy()
    expect(screen.getAllByText('Auto → gemini-y')).toHaveLength(2)
  })

  it('saves the in-chat toggle', async () => {
    await renderTeamTab()

    await act(async () => {
      fireEvent.click(await screen.findByRole('switch'))
    })

    await waitFor(() =>
      expect(requestGateway).toHaveBeenCalledWith('orchestrator.save', {
        config: expect.objectContaining({ enabled: true })
      })
    )
  })

  it('saves the Auto cost/quality balance', async () => {
    await renderTeamTab()

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

  it('rolls the choice back when the save fails', async () => {
    requestGateway.mockImplementation((method: string) =>
      method === 'orchestrator.save'
        ? Promise.reject(new Error('disk full'))
        : method === 'orchestrator.runs'
          ? Promise.resolve({ runs: [] })
          : Promise.resolve(payload(initial))
    )
    await renderTeamTab()

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

describe('Orchestrator runs', () => {
  it('runs a task headlessly from the tab, whether or not the chat tool is enabled', async () => {
    await renderView()

    fireEvent.change(await screen.findByLabelText('Run a task'), { target: { value: '  add a dark mode toggle ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Run' }))

    await waitFor(() =>
      expect(requestGateway).toHaveBeenCalledWith('orchestrator.run', {
        cwd: CWD,
        session_id: 'sess-3',
        task: 'add a dark mode toggle'
      })
    )
  })

  it('shows the live team for a running flow, and stops it', async () => {
    runs = [headlessRun()]
    await renderView()

    const run = await screen.findByTestId('orchestrator-run')
    expect(run.dataset.status).toBe('running')

    const executor = within(run)
      .getAllByTestId('flow-agent')
      .find(el => el.dataset.role === 'executor')!

    expect(executor.dataset.status).toBe('running')
    expect(within(executor).getByText(/write_file src\/theme.ts/)).toBeTruthy()

    // Only one flow per project: the run button waits.
    fireEvent.change(screen.getByLabelText('Run a task'), { target: { value: 'another' } })
    expect((screen.getByRole('button', { name: 'Run' }) as HTMLButtonElement).disabled).toBe(true)

    fireEvent.click(within(run).getByRole('button', { name: /Stop/ }))
    await waitFor(() => expect(requestGateway).toHaveBeenCalledWith('orchestrator.stop', { run_id: 'orch_1' }))
  })

  it('lists past runs and opens their outcome', async () => {
    const finished = headlessRun({
      events: [
        ...headlessRun().events,
        {
          at: 1010,
          type: 'orchestrator.run',
          payload: { run_id: 'flow-1', status: 'approved', round: 1, note: 'Every verifier approved.' }
        }
      ],
      finished_at: 1010,
      id: 'orch_2',
      status: 'approved',
      task: 'fix the login bug'
    })

    runs = [finished, headlessRun({ id: 'orch_1', status: 'failed', error: 'provider down', events: [] })]
    await renderView()

    const items = await screen.findAllByTestId('orchestrator-run-item')
    expect(items.map(item => item.dataset.status)).toEqual(['approved', 'failed'])
    expect(screen.getByText('Every verifier approved.')).toBeTruthy()

    fireEvent.click(items[1]!)
    expect(await screen.findByText('provider down')).toBeTruthy()
    expect(screen.getByText('The flow stopped before any agent started.')).toBeTruthy()
  })

  it('asks for a project when the chat has no workspace', async () => {
    $currentCwd.set('')
    await renderView()
    expect(await screen.findByText('Open a project to run the team')).toBeTruthy()
  })
})
