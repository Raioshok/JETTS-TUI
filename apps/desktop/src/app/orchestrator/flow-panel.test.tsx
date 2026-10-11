// @vitest-environment jsdom
import { act, cleanup, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { $flowRunsBySession, applyFlowRunEvent, applyFlowStageEvent } from '@/store/orchestrator-flow'
import { $activeSessionId } from '@/store/session'
import { $subagentsBySession, upsertSubagent } from '@/store/subagents'

import { FlowPanel, pickPanelRun } from './flow-panel'

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
  render(
    <MemoryRouter>
      <FlowPanel />
    </MemoryRouter>
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
