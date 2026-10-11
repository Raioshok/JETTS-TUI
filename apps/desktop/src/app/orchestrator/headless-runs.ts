// Flows started from the Orchestrator tab run headlessly on the backend
// (`orchestrator.run`, tui_gateway/orchestrator_runs.py) — no chat. The backend
// records the flow's events and a short log per subagent; these helpers turn a
// recorded run into exactly what the Flow views render for a chat's flow.

import { type FlowRun, type RecordedFlowEvent, replayFlowEvents } from '@/store/orchestrator-flow'
import type { SubagentProgress, SubagentStatus } from '@/store/subagents'

export type HeadlessRunStatus = 'approved' | 'changes_requested' | 'failed' | 'interrupted' | 'running'

export interface HeadlessSubagent {
  current_tool: string
  id: string
  model: string
  session_id?: string
  status: string
  stream: { at: number; error: boolean; text: string }[]
}

export interface HeadlessRun {
  cwd: string
  error: string
  events: RecordedFlowEvent[]
  finished_at: null | number
  id: string
  note: string
  started_at: number
  status: HeadlessRunStatus
  subagents: HeadlessSubagent[]
  task: string
  verdict: string
}

/** The run as the Flow views know it. Before the flow's first event (the
 *  coordinator is still starting) there is nothing to replay yet. */
export function toFlowRun(run: HeadlessRun): FlowRun | undefined {
  const flow = replayFlowEvents(run.events)

  if (!flow) {
    return undefined
  }

  // The backend's own status wins: a flow that crashed before reporting a
  // verdict still has to stop reading as running.
  if (run.status !== 'running' && flow.status === 'running') {
    return {
      ...flow,
      status: run.status === 'failed' ? 'failed' : (run.status as FlowRun['status']),
      note: run.error || flow.note,
      finishedAt: run.finished_at ? Math.round(run.finished_at * 1000) : Date.now(),
      stages: flow.stages.map(stage =>
        stage.status === 'running' ? { ...stage, status: 'failed', finishedAt: Date.now() } : stage
      )
    }
  }

  return flow
}

const SUBAGENT_STATUS: Record<string, SubagentStatus> = {
  completed: 'completed',
  failed: 'failed',
  interrupted: 'interrupted',
  queued: 'queued',
  running: 'running'
}

/** Subagent rows in the shape the Flow views join stages against. */
export function toSubagents(run: HeadlessRun): SubagentProgress[] {
  return run.subagents.map(row => {
    const status = SUBAGENT_STATUS[row.status] ?? (row.status === 'error' ? 'failed' : 'running')

    return {
      id: row.id,
      parentId: null,
      goal: '',
      sessionId: row.session_id,
      model: row.model || undefined,
      status,
      taskCount: 1,
      taskIndex: 0,
      startedAt: 0,
      updatedAt: 0,
      filesRead: [],
      filesWritten: [],
      stream: row.stream.map(line => ({
        at: Math.round(line.at * 1000),
        isError: line.error || undefined,
        kind: 'tool' as const,
        text: line.text
      })),
      currentTool: status === 'running' ? row.current_tool || undefined : undefined
    }
  })
}
