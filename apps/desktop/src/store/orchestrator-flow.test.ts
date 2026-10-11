import { beforeEach, describe, expect, it } from 'vitest'

import {
  $flowPanelOpen,
  $flowRunsBySession,
  applyFlowRunEvent,
  applyFlowStageEvent,
  latestStageForRole,
  stagesByRound
} from './orchestrator-flow'

const SID = 'sess-1'

const start = (extra: Record<string, unknown> = {}) =>
  applyFlowRunEvent(SID, {
    run_id: 'run-a',
    status: 'running',
    task: 'add a flag',
    round: 1,
    max_rounds: 3,
    phase: 'work',
    assignments: { executor: { role: 'executor', model: 'coder-x', provider: 'p', auto: true, cost_tier: '$$' } },
    ...extra
  })

const stage = (role: string, phase: string, status: string, extra: Record<string, unknown> = {}) =>
  applyFlowStageEvent(SID, { run_id: 'run-a', role, phase, round: 1, status, model: `${role}-m`, ...extra })

const run = () => $flowRunsBySession.get()[SID]!.at(-1)!

beforeEach(() => {
  $flowRunsBySession.set({})
  $flowPanelOpen.set(false)
})

describe('orchestrator flow store', () => {
  it('reports a newly started flow once, and never opens the sidebar itself', () => {
    expect(start()).toBe(true)
    expect(start({ phase: 'verify' })).toBe(false)
    expect(run().phase).toBe('verify')
    expect($flowPanelOpen.get()).toBe(false)
  })

  it('tracks each role per phase, keeping the spawned subagent id through completion', () => {
    start()
    stage('executor', 'work', 'running')
    stage('executor', 'work', 'running', { subagent_id: 'sa-0-abc' })
    stage('executor', 'work', 'completed', { summary: 'changed a.py' })

    const exec = latestStageForRole(run(), 'executor')!
    expect(exec.status).toBe('completed')
    expect(exec.subagentId).toBe('sa-0-abc')
    expect(exec.summary).toBe('changed a.py')
    expect(exec.finishedAt).toBeGreaterThanOrEqual(exec.startedAt)
    expect(run().stages).toHaveLength(1)
  })

  it("a role's verify stage supersedes its work stage in the same round", () => {
    start()
    stage('reviewer', 'work', 'completed')
    stage('reviewer', 'verify', 'completed', { verdict: 'changes_requested' })

    expect(latestStageForRole(run(), 'reviewer')?.verdict).toBe('changes_requested')
    expect(stagesByRound(run())).toEqual([{ round: 1, stages: run().stages }])
  })

  it('non-clean child statuses read as failures', () => {
    start()
    stage('planner', 'work', 'timeout')
    expect(latestStageForRole(run(), 'planner')?.status).toBe('failed')
  })

  it('ending a run settles any stage still spinning', () => {
    start()
    stage('verifier', 'work', 'running')
    applyFlowRunEvent(SID, { run_id: 'run-a', status: 'interrupted', round: 1, note: 'stopped' })

    expect(run().status).toBe('interrupted')
    expect(run().finishedAt).toBeDefined()
    expect(latestStageForRole(run(), 'verifier')?.status).toBe('interrupted')
  })

  it('keeps assignments from the start event when a later event omits them', () => {
    start()
    applyFlowRunEvent(SID, { run_id: 'run-a', status: 'approved', round: 1 })
    expect(run().assignments.executor?.cost_tier).toBe('$$')
  })

  it('ignores malformed events', () => {
    applyFlowRunEvent(SID, { status: 'running' })
    applyFlowStageEvent(SID, { run_id: 'x', role: 'boss', phase: 'work', round: 1 })
    applyFlowStageEvent('', { run_id: 'x', role: 'planner', phase: 'work', round: 1 })
    expect($flowRunsBySession.get()).toEqual({})
  })

  it('bounds the runs kept per session', () => {
    for (let i = 0; i < 9; i++) {
      applyFlowRunEvent(SID, { run_id: `r${i}`, status: 'running', round: 1 })
    }

    const runs = $flowRunsBySession.get()[SID]!
    expect(runs.length).toBeLessThan(9)
    expect(runs.at(-1)?.id).toBe('r8')
  })
})
