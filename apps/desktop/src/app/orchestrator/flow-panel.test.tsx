// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { $flowRunsBySession, applyFlowRunEvent, applyFlowStageEvent } from '@/store/orchestrator-flow'
import { $activeSessionId } from '@/store/session'
import { $subagentsBySession, upsertSubagent } from '@/store/subagents'

import { FlowPanel, pickPanelRun } from './flow-panel'

const requestGateway = vi.fn()

vi.mock('../gateway/hooks/use-gateway-request', () => ({
  useGatewayRequest: () => ({ requestGateway })
}))

const SID = 'sess-1'

function seedRun(sessionId = SID, runId = 'run-a', startedAt = 1_000) {
  applyFlowRunEvent(sessionId, {
    run_id: runId,
    status: 'running',
    task: 'add a dark mode toggle',
    round: 1,
    max_rounds: 3,
    phase: 'work',
    started_at: startedAt,
    assignments: {
      planner: { role: 'planner', model: 'plan-m', provider: 'p', auto: true, cost_tier: '$$$' },
      executor: { role: 'executor', model: 'exec-m', provider: 'p', auto: true, cost_tier: '$$' },
      reviewer: { role: 'reviewer', model: 'rev-m', provider: 'q', auto: true, cost_tier: '$$' },
      verifier: { role: 'verifier', model: 'ver-m', provider: 'q', auto: true, cost_tier: '$' }
    }
  })
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <FlowPanel />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

const agent = (role: string) => screen.getAllByTestId('flow-agent').find(el => el.dataset.role === role)!

beforeEach(() => {
  $flowRunsBySession.set({})
  $subagentsBySession.set({})
  $activeSessionId.set(SID)
})

afterEach(() => cleanup())

describe('FlowPanel', () => {
  it('shows an empty state with a way to the Orchestrator when no flow ran', () => {
    renderPanel()
    expect(screen.getByText('No flow yet')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Open Orchestrator' })).toBeTruthy()
  })

  it('lists every agent with its model and price tier while they work at once', () => {
    seedRun()

    for (const role of ['planner', 'executor', 'reviewer', 'verifier']) {
      applyFlowStageEvent(SID, { run_id: 'run-a', role, phase: 'work', round: 1, status: 'running' })
    }

    renderPanel()

    expect(screen.getByTestId('flow-run-status').textContent).toContain('Running')
    expect(screen.getByText(/Round 1 of 3/)).toBeTruthy()
    expect(screen.getAllByTestId('flow-agent').filter(el => el.dataset.status === 'running')).toHaveLength(4)
    expect(within(agent('executor')).getByText('exec-m')).toBeTruthy()
    expect(within(agent('executor')).getByText('$$')).toBeTruthy()
  })

  it("streams the agent's live tool from its subagent row", () => {
    seedRun()
    applyFlowStageEvent(SID, {
      run_id: 'run-a',
      role: 'executor',
      phase: 'work',
      round: 1,
      status: 'running',
      subagent_id: 'sa-0-xyz'
    })
    upsertSubagent(
      SID,
      { subagent_id: 'sa-0-xyz', goal: 'g', status: 'running', tool_name: 'write_file', text: 'src/theme.ts' },
      true,
      'subagent.tool'
    )

    renderPanel()

    expect(within(agent('executor')).getByText(/Write File/)).toBeTruthy()
  })

  it('shows verdicts and the final outcome', () => {
    seedRun()
    applyFlowStageEvent(SID, {
      run_id: 'run-a',
      role: 'reviewer',
      phase: 'verify',
      round: 1,
      status: 'completed',
      verdict: 'changes_requested',
      summary: '1. missing null check'
    })
    applyFlowRunEvent(SID, { run_id: 'run-a', status: 'changes_requested', round: 1, note: 'Still failing.' })

    renderPanel()

    expect(screen.getByTestId('flow-run-status').textContent).toContain('Changes requested')
    expect(within(agent('reviewer')).getByText('Changes')).toBeTruthy()
    expect(within(agent('reviewer')).getByText('1. missing null check')).toBeTruthy()
    expect(screen.getByText('Still failing.')).toBeTruthy()
  })

  it('updates live as events arrive', () => {
    seedRun()
    renderPanel()
    expect(agent('planner').dataset.status).toBe('waiting')

    act(() =>
      applyFlowStageEvent(SID, { run_id: 'run-a', role: 'planner', phase: 'work', round: 1, status: 'running' })
    )
    expect(agent('planner').dataset.status).toBe('running')
  })
})

describe('FlowPanel agent detail', () => {
  beforeEach(() => {
    requestGateway.mockReset()
    requestGateway.mockImplementation((method: string, params: { role: string }) =>
      method === 'orchestrator.board'
        ? Promise.resolve({ content: `## ${params.role} notes\n- watching src/theme.ts` })
        : Promise.reject(new Error(`unexpected ${method}`))
    )
  })

  function seedReviewer() {
    seedRun()
    applyFlowRunEvent(SID, { run_id: 'run-a', status: 'running', round: 1, board_dir: '/home/.jettstui/runs/run-a' })
    applyFlowStageEvent(SID, {
      run_id: 'run-a',
      role: 'reviewer',
      phase: 'work',
      round: 1,
      status: 'completed',
      summary: 'gathered edge cases',
      report: '## Pieces\n1. toggle must persist'
    })
    applyFlowStageEvent(SID, {
      run_id: 'run-a',
      role: 'reviewer',
      phase: 'verify',
      round: 1,
      status: 'completed',
      verdict: 'changes_requested',
      summary: '1. persistence missing',
      report: '1. persistence missing\nVERDICT: CHANGES_REQUESTED'
    })
  }

  it('clicking an agent shows every report it filed, newest first, and its board notes', async () => {
    seedReviewer()
    renderPanel()

    fireEvent.click(within(agent('reviewer')).getByRole('button', { name: "Show Reviewer's work" }))

    const detail = screen.getByTestId('flow-agent-detail')
    const reports = within(detail).getAllByTestId('flow-agent-report')
    expect(reports).toHaveLength(2)
    expect(reports[0]!.textContent).toContain('Verify')
    expect(reports[0]!.textContent).toContain('persistence missing')
    expect(reports[1]!.textContent).toContain('toggle must persist')

    await waitFor(() =>
      expect(within(detail).getByTestId('flow-agent-board').textContent).toContain('watching src/theme.ts')
    )
    expect(requestGateway).toHaveBeenCalledWith('orchestrator.board', { run_id: 'run-a', role: 'reviewer' })
  })

  it("shows the running agent's live activity", () => {
    seedRun()
    applyFlowStageEvent(SID, {
      run_id: 'run-a',
      role: 'executor',
      phase: 'work',
      round: 1,
      status: 'running',
      subagent_id: 'sa-0-live'
    })
    upsertSubagent(
      SID,
      { subagent_id: 'sa-0-live', goal: 'g', status: 'running', tool_name: 'patch', text: 'src/theme.ts' },
      true,
      'subagent.tool'
    )
    renderPanel()

    fireEvent.click(within(agent('executor')).getByRole('button'))
    expect(screen.getByTestId('flow-agent-activity').textContent).toContain('Patch')
  })

  it('timeline rows open the same detail, and Back returns to the overview', () => {
    seedReviewer()
    renderPanel()

    const timelineRow = screen
      .getAllByRole('button')
      .find(el => el.textContent?.includes('Reviewer') && !el.closest('[data-testid="flow-agent"]'))!

    fireEvent.click(timelineRow)
    expect(screen.getByTestId('flow-agent-detail')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Back to agents' }))
    expect(screen.queryByTestId('flow-agent-detail')).toBeNull()
    expect(screen.getAllByTestId('flow-agent')).toHaveLength(4)
  })
})

describe('pickPanelRun', () => {
  it("prefers the active chat's flow, else a flow still running elsewhere", () => {
    seedRun('other', 'run-b', 1_000)
    expect(pickPanelRun($flowRunsBySession.get(), SID)?.run.id).toBe('run-b')

    seedRun(SID, 'run-a', 2_000)
    expect(pickPanelRun($flowRunsBySession.get(), SID)?.run.id).toBe('run-a')

    // No active flow: the newest one still running anywhere, then nothing.
    expect(pickPanelRun($flowRunsBySession.get(), 'nobody')?.run.id).toBe('run-a')
    applyFlowRunEvent(SID, { run_id: 'run-a', status: 'approved', round: 1 })
    applyFlowRunEvent('other', { run_id: 'run-b', status: 'approved', round: 1 })
    expect(pickPanelRun($flowRunsBySession.get(), 'nobody')).toBeUndefined()
  })
})
