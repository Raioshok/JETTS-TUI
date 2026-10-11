// Shapes of the `spec.list` / `spec.get` RPCs (jettstui/specs.py owns the
// truth) and the pure helpers the Specs page uses to decide what to offer and
// which `/spec` command performs it.

export const SPEC_STAGES = ['requirements', 'design', 'tasks'] as const

export type SpecStage = (typeof SPEC_STAGES)[number]
export type SpecPhase = 'design' | 'done' | 'implementation' | 'requirements' | 'tasks'
export type SpecTaskStatus = 'completed' | 'in_progress' | 'not_started' | 'queued'
export type SpecCreateMode = 'auto' | 'quick' | 'step'

export interface SpecProgress {
  completed: number
  in_progress: number
  optional: number
  total: number
}

export interface SpecSummary {
  documents: Record<SpecStage, boolean>
  legacy: boolean
  name: string
  path: string
  phase: SpecPhase
  progress: SpecProgress
  spec_type: string
  workflow_type: string
}

export interface SpecTask {
  depth: number
  details: string[]
  id: string
  line: number
  optional: boolean
  requirements: string[]
  status: SpecTaskStatus
  title: string
}

export interface SpecDetail extends SpecSummary {
  content: Record<SpecStage, string>
  files: Record<SpecStage, string>
  next_task: null | string
  tasks: SpecTask[]
}

/** The `/spec` subcommand each creation mode maps to. */
const CREATE_VERB: Record<SpecCreateMode, string> = { auto: 'auto', quick: 'quick', step: 'new' }

export function createCommand(mode: SpecCreateMode, feature: string): string {
  return `/spec ${CREATE_VERB[mode]} ${feature.replace(/\s+/g, ' ').trim()}`
}

export function approveCommand(name: string, stage: SpecStage): string {
  return `/spec approve ${name} ${stage}`
}

export function refineCommand(name: string, stage: SpecStage, feedback: string): string {
  return `/spec refine ${name} ${stage} ${feedback.replace(/\s+/g, ' ').trim()}`
}

export function startTaskCommand(name: string, taskId: string): string {
  return `/spec task ${name} ${taskId}`
}

export function runAllCommand(name: string, includeOptional = false): string {
  return `/spec run ${name}${includeOptional ? ' --optional' : ''}`
}

/** The stage after `stage` in Kiro's order, or null after tasks. */
export function nextStage(stage: SpecStage): null | SpecStage {
  const index = SPEC_STAGES.indexOf(stage)

  return SPEC_STAGES[index + 1] ?? null
}

/** A stage can be approved once its document exists and the next one doesn't
 *  yet — approving is what produces the next document. Tasks need no approval
 *  to start (Kiro's "Start task" works as soon as the list exists). */
export function canApprove(spec: Pick<SpecSummary, 'documents'>, stage: SpecStage): boolean {
  const next = nextStage(stage)

  return Boolean(next) && spec.documents[stage] && !spec.documents[next!]
}

/** The document tab a spec should open on: the newest one written. */
export function currentStage(spec: Pick<SpecSummary, 'documents'>): SpecStage {
  return [...SPEC_STAGES].reverse().find(stage => spec.documents[stage]) ?? 'requirements'
}

export type SpecNextAction =
  | { kind: 'approve'; stage: SpecStage }
  | { kind: 'done' }
  | { kind: 'start'; taskId: string }
  | { kind: 'wait'; stage: SpecStage }

/** The one step that moves the spec forward — the page's "Next step" button. */
export function nextAction(spec: SpecDetail): SpecNextAction {
  if (spec.documents.tasks) {
    return spec.next_task ? { kind: 'start', taskId: spec.next_task } : { kind: 'done' }
  }

  for (const stage of ['design', 'requirements'] as const) {
    if (spec.documents[stage]) {
      return { kind: 'approve', stage }
    }
  }

  return { kind: 'wait', stage: 'requirements' }
}

/** Leaf tasks can be started; a parent runs through its sub-tasks. */
export function isStartable(task: SpecTask): boolean {
  return task.status !== 'completed'
}
