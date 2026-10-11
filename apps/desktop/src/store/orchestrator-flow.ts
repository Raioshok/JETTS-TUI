import { atom } from 'nanostores'

import { Codecs, persistentAtom } from '@/lib/persisted'

// Live state of orchestrator flows (agent/orchestrator.py), fed by the
// display-only `orchestrator.run` / `orchestrator.stage` gateway events and
// rendered by the Flow sidebar. Keyed by the session that ran `orchestrate`.

export const FLOW_ROLES = ['planner', 'executor', 'reviewer', 'verifier'] as const

export type FlowRole = (typeof FLOW_ROLES)[number]
export type FlowPhase = 'verify' | 'work'
export type FlowRunStatus = 'approved' | 'changes_requested' | 'failed' | 'interrupted' | 'running'
export type FlowStageStatus = 'completed' | 'failed' | 'interrupted' | 'running'
export type FlowVerdict = 'approved' | 'changes_requested' | 'unknown'

export interface FlowAssignment {
  auto: boolean
  cost_tier: string
  model: string
  provider: string
  reason: string
  role: FlowRole
}

export interface FlowStage {
  /** `${round}:${phase}:${role}` — one row per role per phase per round. */
  key: string
  role: FlowRole
  round: number
  phase: FlowPhase
  status: FlowStageStatus
  model: string
  provider: string
  /** Joins the stage to its live subagent row ($subagentsBySession). */
  subagentId?: string
  verdict?: FlowVerdict
  summary?: string
  /** The stage's full (bounded) report — the agent detail view's body. */
  report?: string
  startedAt: number
  finishedAt?: number
}

export interface FlowRun {
  id: string
  task: string
  status: FlowRunStatus
  round: number
  maxRounds: number
  phase: FlowPhase | ''
  balance: string
  boardDir: string
  note: string
  startedAt: number
  finishedAt?: number
  assignments: Partial<Record<FlowRole, FlowAssignment>>
  stages: FlowStage[]
}

type Payload = Record<string, unknown>

const MAX_RUNS_PER_SESSION = 5

export const $flowRunsBySession = atom<Record<string, FlowRun[]>>({})

/** Flow sidebar visibility — persisted like the other right-rail panes. */
export const $flowPanelOpen = persistentAtom('jettstui.desktop.flowPanelOpen', false, Codecs.bool)

export const setFlowPanelOpen = (open: boolean) => $flowPanelOpen.set(open)
export const toggleFlowPanel = () => $flowPanelOpen.set(!$flowPanelOpen.get())

const str = (v: unknown) => (typeof v === 'string' ? v : '')
const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : undefined)

const isRole = (v: unknown): v is FlowRole => FLOW_ROLES.includes(v as FlowRole)

const asPhase = (v: unknown): FlowPhase | '' => (v === 'work' || v === 'verify' ? v : '')

const asRunStatus = (v: unknown): FlowRunStatus =>
  v === 'approved' || v === 'changes_requested' || v === 'failed' || v === 'interrupted' ? v : 'running'

// Child statuses come straight from the delegate lifecycle ("completed",
// "error", "timeout", "interrupted", …); anything not clean is a failure.
const asStageStatus = (v: unknown): FlowStageStatus =>
  v === 'running' || v === 'completed' || v === 'interrupted' ? v : 'failed'

const asVerdict = (v: unknown): FlowVerdict | undefined =>
  v === 'approved' || v === 'changes_requested' || v === 'unknown' ? v : undefined

function asAssignments(v: unknown): FlowRun['assignments'] {
  if (!v || typeof v !== 'object') {
    return {}
  }

  const out: FlowRun['assignments'] = {}

  for (const [role, raw] of Object.entries(v as Payload)) {
    if (!isRole(role) || !raw || typeof raw !== 'object') {
      continue
    }

    const a = raw as Payload

    out[role] = {
      auto: a.auto === true,
      cost_tier: str(a.cost_tier),
      model: str(a.model),
      provider: str(a.provider),
      reason: str(a.reason),
      role
    }
  }

  return out
}

const secondsToMs = (v: unknown) => {
  const s = num(v)

  return s === undefined ? undefined : Math.round(s * 1000)
}

function emptyRun(id: string, now: number): FlowRun {
  return {
    id,
    task: '',
    status: 'running',
    round: 0,
    maxRounds: 1,
    phase: '',
    balance: '',
    boardDir: '',
    note: '',
    startedAt: now,
    assignments: {},
    stages: []
  }
}

function updateRun(sessionId: string, runId: string, update: (run: FlowRun, isNew: boolean) => FlowRun) {
  const map = $flowRunsBySession.get()
  const runs = map[sessionId] ?? []
  const index = runs.findIndex(run => run.id === runId)
  const isNew = index < 0
  const next = update(isNew ? emptyRun(runId, Date.now()) : runs[index], isNew)
  const merged = isNew ? [...runs, next].slice(-MAX_RUNS_PER_SESSION) : runs.map((run, i) => (i === index ? next : run))

  $flowRunsBySession.set({ ...map, [sessionId]: merged })

  return isNew
}

/** Apply an `orchestrator.run` event (flow start, phase change, final verdict).
 *  Returns true when the event started a flow this window hadn't seen, so the
 *  caller can OFFER the sidebar (a background event never opens surfaces). */
export function applyFlowRunEvent(sessionId: string, payload: Payload): boolean {
  const runId = str(payload.run_id)

  if (!sessionId || !runId) {
    return false
  }

  const status = asRunStatus(payload.status)

  const isNew = updateRun(sessionId, runId, (run, fresh) => {
    const assignments = asAssignments(payload.assignments)
    const ended = status !== 'running'

    return {
      ...run,
      task: str(payload.task) || run.task,
      status,
      round: num(payload.round) ?? run.round,
      maxRounds: num(payload.max_rounds) ?? run.maxRounds,
      phase: ended ? run.phase : asPhase(payload.phase) || run.phase,
      balance: str(payload.balance) || run.balance,
      boardDir: str(payload.board_dir) || run.boardDir,
      note: str(payload.note) || run.note,
      startedAt: fresh ? (secondsToMs(payload.started_at) ?? run.startedAt) : run.startedAt,
      finishedAt: ended ? (run.finishedAt ?? Date.now()) : undefined,
      assignments: Object.keys(assignments).length ? assignments : run.assignments,
      // A run that ends mid-phase (failure / interrupt) leaves no stage spinning.
      stages: ended
        ? run.stages.map(stage =>
            stage.status === 'running'
              ? { ...stage, status: status === 'interrupted' ? 'interrupted' : 'failed', finishedAt: Date.now() }
              : stage
          )
        : run.stages
    }
  })

  return isNew && status === 'running'
}

/** Apply an `orchestrator.stage` event (stage started / spawned / finished). */
export function applyFlowStageEvent(sessionId: string, payload: Payload) {
  const runId = str(payload.run_id)
  const role = payload.role
  const phase = asPhase(payload.phase)
  const round = num(payload.round)

  if (!sessionId || !runId || !isRole(role) || !phase || round === undefined) {
    return
  }

  const key = `${round}:${phase}:${role}`
  const now = Date.now()

  updateRun(sessionId, runId, run => {
    const prev = run.stages.find(stage => stage.key === key)
    const status = asStageStatus(payload.status)

    const stage: FlowStage = {
      key,
      role,
      round,
      phase,
      status,
      model: str(payload.model_used) || str(payload.model) || prev?.model || '',
      provider: str(payload.provider) || prev?.provider || '',
      subagentId: str(payload.subagent_id) || prev?.subagentId,
      verdict: asVerdict(payload.verdict) ?? prev?.verdict,
      summary: str(payload.summary) || prev?.summary,
      report: str(payload.report) || prev?.report,
      startedAt: prev?.startedAt ?? now,
      finishedAt: status === 'running' ? undefined : (prev?.finishedAt ?? now)
    }

    return {
      ...run,
      round: Math.max(run.round, round),
      stages: prev ? run.stages.map(s => (s.key === key ? stage : s)) : [...run.stages, stage]
    }
  })
}

export function latestFlowRun(runs: readonly FlowRun[] | undefined): FlowRun | undefined {
  return runs?.at(-1)
}

/** The role's newest stage in a run — what its agent card shows. */
export function latestStageForRole(run: FlowRun, role: FlowRole): FlowStage | undefined {
  let latest: FlowStage | undefined

  for (const stage of run.stages) {
    if (stage.role !== role) {
      continue
    }

    if (
      !latest ||
      stage.round > latest.round ||
      (stage.round === latest.round && stage.phase === 'verify' && latest.phase === 'work')
    ) {
      latest = stage
    }
  }

  return latest
}

/** Stages grouped per round, oldest first — the sidebar's timeline. */
export function stagesByRound(run: FlowRun): { round: number; stages: FlowStage[] }[] {
  const rounds = new Map<number, FlowStage[]>()

  for (const stage of run.stages) {
    rounds.set(stage.round, [...(rounds.get(stage.round) ?? []), stage])
  }

  return [...rounds.entries()].sort(([a], [b]) => a - b).map(([round, stages]) => ({ round, stages }))
}

export function clearSessionFlows(sessionId: string) {
  const map = $flowRunsBySession.get()

  if (!(sessionId in map)) {
    return
  }

  const { [sessionId]: _drop, ...rest } = map
  $flowRunsBySession.set(rest)
}
