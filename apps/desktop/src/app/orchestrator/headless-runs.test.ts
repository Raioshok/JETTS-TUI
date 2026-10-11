import { describe, expect, it } from 'vitest'

import { type HeadlessRun, toFlowRun, toSubagents } from './headless-runs'

function run(overrides: Partial<HeadlessRun> = {}): HeadlessRun {
  return {
    cwd: '/w',
    error: '',
    events: [
      {
        at: 100,
        type: 'orchestrator.run',
        payload: { run_id: 'f', status: 'running', task: 't', round: 1, started_at: 100 }
      },
      {
        at: 101,
        type: 'orchestrator.stage',
        payload: { run_id: 'f', role: 'planner', phase: 'work', round: 1, status: 'running' }
      },
      {
        at: 105,
        type: 'orchestrator.stage',
        payload: { run_id: 'f', role: 'planner', phase: 'work', round: 1, status: 'completed' }
      }
    ],
    finished_at: null,
    id: 'orch',
    note: '',
    started_at: 100,
    status: 'running',
    subagents: [],
    task: 't',
    verdict: '',
    ...overrides
  }
}

describe('headless orchestrator runs', () => {
  it('replays recorded events with their recorded times, not the time of the poll', () => {
    const flow = toFlowRun(run())!
    const planner = flow.stages[0]!

    expect(flow.startedAt).toBe(100_000)
    expect([planner.startedAt, planner.finishedAt]).toEqual([101_000, 105_000])
  })

  it('a flow that died without a verdict stops reading as running', () => {
    const flow = toFlowRun(
      run({
        status: 'failed',
        error: 'provider down',
        finished_at: 110,
        events: run().events.slice(0, 2)
      })
    )!

    expect(flow.status).toBe('failed')
    expect(flow.note).toBe('provider down')
    expect(flow.stages.every(stage => stage.status !== 'running')).toBe(true)
  })

  it('has nothing to show before the first event', () => {
    expect(toFlowRun(run({ events: [] }))).toBeUndefined()
  })

  it('maps subagent logs onto the rows the Flow views join against', () => {
    const [row] = toSubagents(
      run({
        subagents: [
          {
            current_tool: 'patch',
            id: 'sa',
            model: 'm',
            status: 'running',
            stream: [{ at: 2, error: true, text: 'patch x' }]
          }
        ]
      })
    )

    expect(row).toMatchObject({ id: 'sa', status: 'running', currentTool: 'patch' })
    expect(row!.stream).toEqual([{ at: 2000, isError: true, kind: 'tool', text: 'patch x' }])
  })
})
