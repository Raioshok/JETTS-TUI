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

/** The spec command each creation mode maps to. Commands are `/spec`
 *  arguments; the page runs them headlessly through `spec.run`. */
const CREATE_VERB: Record<SpecCreateMode, string> = { auto: 'auto', quick: 'quick', step: 'new' }

export function createCommand(mode: SpecCreateMode, feature: string): string {
  return `${CREATE_VERB[mode]} ${feature.replace(/\s+/g, ' ').trim()}`
}

export function approveCommand(name: string, stage: SpecStage): string {
  return `approve ${name} ${stage}`
}

export function refineCommand(name: string, stage: SpecStage, feedback: string): string {
  return `refine ${name} ${stage} ${feedback.replace(/\s+/g, ' ').trim()}`
}

export function startTaskCommand(name: string, taskId: string): string {
  return `task ${name} ${taskId}`
}

/** Redo a step that never got written (a stopped or failed draft). */
export function resumeCommand(name: string): string {
  return `resume ${name}`
}

export function runAllCommand(name: string, includeOptional = false): string {
  return `run ${name}${includeOptional ? ' --optional' : ''}`
}

/** The stage after `stage` in workflow order, or null after tasks. */
export function nextStage(stage: SpecStage): null | SpecStage {
  const index = SPEC_STAGES.indexOf(stage)

  return SPEC_STAGES[index + 1] ?? null
}

/** A stage can be approved once its document exists and the next one doesn't
 *  yet — approving is what produces the next document. Tasks need no approval
 *  to start ("Start task" works as soon as the list exists). */
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

/** Changes whenever the agent moves the spec forward (a document appears, a
 *  task starts or finishes) — what clears the "working in chat" state. */
export function specSignature(spec: Pick<SpecSummary, 'documents' | 'phase' | 'progress'>): string {
  const docs = SPEC_STAGES.map(stage => (spec.documents[stage] ? 1 : 0)).join('')

  return `${spec.phase}|${docs}|${spec.progress.completed}|${spec.progress.in_progress}`
}

export const SPEC_STEPS = ['requirements', 'design', 'tasks', 'build'] as const

export type SpecStep = (typeof SPEC_STEPS)[number]
export type SpecStepState = 'done' | 'drafting' | 'review' | 'upcoming'

/** Where each workflow step stands: written and approved (done), waiting on
 *  the user (review), being written (drafting) or not reached yet. Only a
 *  running agent makes a missing document read as "being written". */
export function stepStates(
  spec: Pick<SpecSummary, 'documents' | 'phase' | 'progress'>,
  running = false
): Record<SpecStep, SpecStepState> {
  const { documents: docs, phase, progress } = spec
  const started = progress.completed > 0 || progress.in_progress > 0

  return {
    requirements: docs.design ? 'done' : docs.requirements ? 'review' : running ? 'drafting' : 'upcoming',
    design: docs.tasks ? 'done' : docs.design ? 'review' : 'upcoming',
    tasks: docs.tasks ? (started ? 'done' : 'review') : 'upcoming',
    build: phase === 'done' ? 'done' : started ? 'drafting' : 'upcoming'
  }
}

/** The document a step shows; building happens on the task list. */
export function stepStage(step: SpecStep): SpecStage {
  return step === 'build' ? 'tasks' : step
}

export type SpecRunStatus = 'completed' | 'failed' | 'interrupted' | 'running'

/** A headless agent run started from the Specs page (`spec.run`). */
export interface SpecRun {
  activity: { at: number; kind: string; text: string }[]
  error: string
  finished_at: null | number
  id: string
  label: string
  mode: string
  /** The spec command that redoes this run's step (Retry). */
  retry_args: string
  spec: string
  started_at: number
  status: SpecRunStatus
  summary: string
}

/** Each spec's newest run — `spec.runs` lists newest first. */
export function latestRunBySpec(runs: readonly SpecRun[]): Record<string, SpecRun> {
  const out: Record<string, SpecRun> = {}

  for (const run of runs) {
    out[run.spec] ??= run
  }

  return out
}
