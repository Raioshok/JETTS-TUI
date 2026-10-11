import { useStore } from '@nanostores/react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'

import { useElapsedSeconds } from '@/components/chat/activity-timer'
import { ActivityTimerText } from '@/components/chat/activity-timer-text'
import { Button } from '@/components/ui/button'
import { Codicon } from '@/components/ui/codicon'
import { CopyButton } from '@/components/ui/copy-button'
import { GlyphSpinner } from '@/components/ui/glyph-spinner'
import { Tip } from '@/components/ui/tooltip'
import { useI18n } from '@/i18n'
import { AlertCircle, CheckCircle2 } from '@/lib/icons'
import { cn } from '@/lib/utils'
import {
  $flowRunsBySession,
  FLOW_ROLES,
  type FlowPhase,
  type FlowRole,
  type FlowRun,
  type FlowStage,
  latestStageForRole,
  setFlowPanelOpen,
  stagesByRound
} from '@/store/orchestrator-flow'
import { $activeSessionId } from '@/store/session'
import { $subagentsBySession, type SubagentProgress } from '@/store/subagents'

import { PaneEmptyState, RightSidebarSectionHeader } from '../right-sidebar'
import { navigateToWorkspacePage, ORCHESTRATOR_ROUTE } from '../routes'
import { SidebarPanelLabel } from '../shell/sidebar-label'

/** The run the sidebar shows: the active chat's newest flow, else whichever
 *  flow is still running elsewhere (a background chat), else nothing. */
export function pickPanelRun(runsBySession: Record<string, FlowRun[]>, activeSessionId: null | string) {
  const active = activeSessionId ? runsBySession[activeSessionId]?.at(-1) : undefined

  if (active) {
    return { run: active, sessionId: activeSessionId! }
  }

  let best: { run: FlowRun; sessionId: string } | undefined

  for (const [sessionId, runs] of Object.entries(runsBySession)) {
    for (const run of runs) {
      if (run.status === 'running' && (!best || run.startedAt > best.run.startedAt)) {
        best = { run, sessionId }
      }
    }
  }

  return best
}

export function FlowPanel() {
  const { t } = useI18n()
  const f = t.orchestrator.flow
  const runsBySession = useStore($flowRunsBySession)
  const activeSessionId = useStore($activeSessionId)
  const subagentsBySession = useStore($subagentsBySession)
  const picked = pickPanelRun(runsBySession, activeSessionId)

  return (
    <aside
      aria-label={f.title}
      className="flex h-full w-full min-w-0 flex-col overflow-hidden bg-(--ui-sidebar-surface-background) text-(--ui-text-tertiary)"
      data-testid="flow-panel"
    >
      <RightSidebarSectionHeader>
        <div className="flex min-w-0 flex-1">
          <SidebarPanelLabel>{f.title}</SidebarPanelLabel>
        </div>
        <Tip label={f.close}>
          <Button aria-label={f.close} onClick={() => setFlowPanelOpen(false)} size="icon-xs" variant="ghost">
            <Codicon name="close" size="0.8125rem" />
          </Button>
        </Tip>
      </RightSidebarSectionHeader>
      {picked ? <FlowRunView run={picked.run} subagents={subagentsBySession[picked.sessionId] ?? []} /> : <FlowEmpty />}
    </aside>
  )
}

function FlowEmpty() {
  const { t } = useI18n()
  const f = t.orchestrator.flow
  const navigate = useNavigate()

  return (
    <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 px-4 text-center">
      <PaneEmptyState label={f.emptyTitle} />
      <p className="max-w-56 text-[0.68rem] leading-relaxed text-(--ui-text-quaternary)">{f.emptyBody}</p>
      <Button onClick={() => navigateToWorkspacePage(navigate, ORCHESTRATOR_ROUTE)} size="sm" variant="secondary">
        {f.openOrchestrator}
      </Button>
    </div>
  )
}

interface FlowRunViewProps {
  run: FlowRun
  subagents: readonly SubagentProgress[]
}

function FlowRunView({ run, subagents }: FlowRunViewProps) {
  const { t } = useI18n()
  const f = t.orchestrator.flow
  const running = run.status === 'running'
  const elapsed = useElapsedSeconds(running, `flow:${run.id}`, run.startedAt)
  const finishedSeconds = run.finishedAt ? Math.max(0, Math.round((run.finishedAt - run.startedAt) / 1000)) : 0
  const subagentById = new Map(subagents.map(s => [s.id, s]))

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto overflow-x-hidden px-2.5 pb-4">
      <section className="grid gap-1.5 pb-3 pt-1">
        <div className="flex items-center gap-2">
          <RunStatusChip status={run.status} />
          <span className="text-[0.66rem] text-(--ui-text-tertiary)">
            {f.roundOf(Math.max(1, run.round), run.maxRounds)}
            {running && run.phase ? ` · ${f.phase[run.phase]}` : ''}
          </span>
          <span className="ml-auto">
            <ActivityTimerText seconds={running ? elapsed : finishedSeconds} />
          </span>
        </div>
        <p className="line-clamp-3 text-[0.72rem] leading-snug text-(--ui-text-secondary)" title={run.task}>
          {run.task}
        </p>
        <RoundStepper run={run} />
      </section>

      <section aria-label={f.agents} className="grid gap-1">
        <SectionLabel>{running ? f.agentsLive : f.agents}</SectionLabel>
        <ul className="grid gap-1">
          {FLOW_ROLES.map(role => {
            const stage = latestStageForRole(run, role)

            return (
              <AgentCard
                assignmentModel={run.assignments[role]?.model ?? ''}
                costTier={run.assignments[role]?.cost_tier ?? ''}
                key={role}
                role={role}
                stage={stage}
                subagent={stage?.subagentId ? subagentById.get(stage.subagentId) : undefined}
              />
            )
          })}
        </ul>
      </section>

      {run.note && !running && (
        <p className="mt-3 rounded-md bg-(--ui-bg-tertiary) px-2.5 py-2 text-[0.68rem] leading-relaxed text-(--ui-text-secondary)">
          {run.note}
        </p>
      )}

      <section aria-label={f.timeline} className="mt-4 grid gap-1">
        <SectionLabel>{f.timeline}</SectionLabel>
        {stagesByRound(run)
          .slice()
          .reverse()
          .map(({ round, stages }) => (
            <div className="grid gap-0.5" key={round}>
              <div className="px-1 pt-1 text-[0.6rem] font-medium uppercase tracking-[0.06em] text-(--ui-text-quaternary)">
                {f.roundLabel(round)}
              </div>
              {(['verify', 'work'] as const).map(phase =>
                stages
                  .filter(stage => stage.phase === phase)
                  .map(stage => <TimelineRow key={stage.key} stage={stage} />)
              )}
            </div>
          ))}
      </section>

      {run.boardDir && (
        <div className="mt-4 flex min-w-0 items-center gap-1.5 px-1">
          <Codicon className="shrink-0 text-(--ui-text-quaternary)" name="notebook" size="0.75rem" />
          <span
            className="min-w-0 flex-1 truncate font-mono text-[0.6rem] text-(--ui-text-quaternary)"
            title={run.boardDir}
          >
            {f.board}: {run.boardDir}
          </span>
          <CopyButton appearance="icon" label={f.copyBoard} text={run.boardDir} />
        </div>
      )}
    </div>
  )
}

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <div className="px-1 text-[0.62rem] font-semibold uppercase tracking-[0.07em] text-(--ui-text-quaternary)">
      {children}
    </div>
  )
}

const RUN_TONE: Record<FlowRun['status'], string> = {
  approved: 'bg-emerald-500/12 text-emerald-700 dark:text-emerald-300',
  changes_requested: 'bg-amber-500/14 text-amber-700 dark:text-amber-300',
  failed: 'bg-destructive/12 text-destructive',
  interrupted: 'bg-(--ui-bg-tertiary) text-(--ui-text-secondary)',
  running: 'bg-(--ui-bg-tertiary) text-(--ui-text-primary)'
}

function RunStatusChip({ status }: { status: FlowRun['status'] }) {
  const { t } = useI18n()

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[0.62rem] font-medium',
        RUN_TONE[status]
      )}
      data-testid="flow-run-status"
    >
      {status === 'running' && <GlyphSpinner ariaLabel={t.orchestrator.flow.status.running} spinner="breathe" />}
      {t.orchestrator.flow.status[status]}
    </span>
  )
}

/** One segment per phase per round: the workflow at a glance. */
function RoundStepper({ run }: { run: FlowRun }) {
  const { t } = useI18n()
  const f = t.orchestrator.flow
  const rounds = Math.max(run.maxRounds, run.round, 1)

  const segmentTone = (round: number, phase: FlowPhase) => {
    const stages = run.stages.filter(s => s.round === round && s.phase === phase)

    if (stages.length === 0) {
      return 'bg-(--ui-bg-tertiary)'
    }

    if (stages.some(s => s.status === 'running')) {
      return 'animate-pulse bg-(--ui-text-tertiary)'
    }

    if (stages.some(s => s.status === 'failed')) {
      return 'bg-destructive/70'
    }

    if (phase === 'verify') {
      return stages.every(s => s.verdict === 'approved') ? 'bg-emerald-500/80' : 'bg-amber-500/80'
    }

    return 'bg-(--ui-text-quaternary)'
  }

  return (
    <div aria-label={f.progress} className="flex items-center gap-1 pt-1" role="img">
      {Array.from({ length: rounds }, (_, i) => i + 1).map(round => (
        <div className="flex flex-1 gap-0.5" key={round} title={f.roundLabel(round)}>
          {(['work', 'verify'] as const).map(phase => (
            <span
              className={cn('h-1 flex-1 rounded-full transition-colors', segmentTone(round, phase))}
              key={phase}
              title={`${f.roundLabel(round)} · ${f.phase[phase]}`}
            />
          ))}
        </div>
      ))}
    </div>
  )
}

function stageGlyph(stage: FlowStage | undefined, label: string): ReactNode {
  if (!stage) {
    return <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-(--ui-text-quaternary)/60" />
  }

  if (stage.status === 'running') {
    return (
      <GlyphSpinner
        ariaLabel={label}
        className="size-3.5 shrink-0 text-[0.95rem] text-muted-foreground/80"
        spinner="breathe"
      />
    )
  }

  if (stage.status === 'failed' || stage.status === 'interrupted') {
    return <AlertCircle aria-label={label} className="size-3.5 shrink-0 text-destructive" />
  }

  if (stage.verdict === 'changes_requested' || stage.verdict === 'unknown') {
    return <AlertCircle aria-label={label} className="size-3.5 shrink-0 text-amber-600 dark:text-amber-400" />
  }

  return <CheckCircle2 aria-label={label} className="size-3.5 shrink-0 text-emerald-600/85 dark:text-emerald-400/85" />
}

interface AgentCardProps {
  assignmentModel: string
  costTier: string
  role: FlowRole
  stage: FlowStage | undefined
  subagent: SubagentProgress | undefined
}

function AgentCard({ assignmentModel, costTier, role, stage, subagent }: AgentCardProps) {
  const { t } = useI18n()
  const o = t.orchestrator
  const f = o.flow
  const running = stage?.status === 'running'
  const elapsed = useElapsedSeconds(running, stage ? `flow-stage:${stage.key}` : undefined, stage?.startedAt)
  const model = stage?.model || assignmentModel || f.sessionModel
  const statusLabel = stage ? f.stage[stage.status] : f.waiting
  // The child's newest activity line (`Write File("src/x.ts")`), formatted by the subagent store.
  const liveLine = running ? subagent?.stream.at(-1)?.text || subagent?.currentTool : undefined
  const detail = liveLine || (stage?.status === 'running' ? f.starting : stage?.summary)

  return (
    <li
      className={cn(
        'grid gap-1 rounded-md px-2 py-1.5 transition-colors',
        running ? 'bg-(--ui-bg-tertiary)/70' : 'hover:bg-(--ui-bg-tertiary)/40'
      )}
      data-role={role}
      data-status={stage?.status ?? 'waiting'}
      data-testid="flow-agent"
    >
      <div className="flex min-w-0 items-center gap-2">
        {stageGlyph(stage, statusLabel)}
        <span className="truncate text-[0.74rem] font-medium text-(--ui-text-primary)">{o.roles[role].title}</span>
        {stage && (
          <span className="shrink-0 rounded-sm bg-(--ui-bg-tertiary) px-1 py-px text-[0.56rem] uppercase tracking-[0.05em] text-(--ui-text-tertiary)">
            {f.phase[stage.phase]}
          </span>
        )}
        {stage?.verdict && stage.status === 'completed' && <VerdictChip verdict={stage.verdict} />}
        <span className="ml-auto shrink-0">{running && <ActivityTimerText seconds={elapsed} />}</span>
      </div>
      <div className="flex min-w-0 items-center gap-1.5 pl-5.5">
        <span className="min-w-0 truncate font-mono text-[0.62rem] text-(--ui-text-tertiary)" title={model}>
          {model}
        </span>
        {costTier && (
          <span className="shrink-0 text-[0.6rem] text-(--ui-text-quaternary)" title={f.costTier}>
            {costTier}
          </span>
        )}
      </div>
      {detail && (
        <p
          className={cn(
            'line-clamp-2 pl-5.5 text-[0.66rem] leading-snug',
            liveLine ? 'font-mono text-(--ui-text-secondary)' : 'text-(--ui-text-tertiary)'
          )}
          title={detail}
        >
          {detail}
        </p>
      )}
    </li>
  )
}

function VerdictChip({ verdict }: { verdict: NonNullable<FlowStage['verdict']> }) {
  const { t } = useI18n()

  return (
    <span
      className={cn(
        'shrink-0 rounded-sm px-1 py-px text-[0.56rem] font-medium',
        verdict === 'approved'
          ? 'bg-emerald-500/12 text-emerald-700 dark:text-emerald-300'
          : 'bg-amber-500/14 text-amber-700 dark:text-amber-300'
      )}
    >
      {t.orchestrator.flow.verdict[verdict]}
    </span>
  )
}

function TimelineRow({ stage }: { stage: FlowStage }) {
  const { t } = useI18n()
  const o = t.orchestrator
  const seconds = stage.finishedAt ? Math.max(0, Math.round((stage.finishedAt - stage.startedAt) / 1000)) : undefined

  return (
    <div className="flex min-w-0 items-center gap-2 rounded px-1 py-0.5" title={stage.summary}>
      {stageGlyph(stage, o.flow.stage[stage.status])}
      <span className="w-12 shrink-0 text-[0.6rem] uppercase tracking-[0.05em] text-(--ui-text-quaternary)">
        {o.flow.phase[stage.phase]}
      </span>
      <span className="min-w-0 flex-1 truncate text-[0.68rem] text-(--ui-text-secondary)">
        {o.roles[stage.role].title}
      </span>
      {stage.verdict && stage.status === 'completed' && <VerdictChip verdict={stage.verdict} />}
      {seconds !== undefined && <ActivityTimerText seconds={seconds} />}
    </div>
  )
}
