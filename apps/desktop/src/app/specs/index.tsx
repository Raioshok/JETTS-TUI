import { useStore } from '@nanostores/react'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { type ReactNode, useEffect, useState } from 'react'

import { useElapsedSeconds } from '@/components/chat/activity-timer'
import { ActivityTimerText } from '@/components/chat/activity-timer-text'
import { CompactMarkdown } from '@/components/chat/compact-markdown'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Codicon } from '@/components/ui/codicon'
import { GlyphSpinner } from '@/components/ui/glyph-spinner'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { Skeleton } from '@/components/ui/skeleton'
import { useI18n } from '@/i18n'
import { normalizeOrLocalPreviewTarget } from '@/lib/local-preview'
import { cn } from '@/lib/utils'
import { notify, notifyError } from '@/store/notifications'
import { openPreview } from '@/store/preview'
import { $activeSessionId, $currentCwd, $gatewayState } from '@/store/session'
import { $workspaceChangeTick } from '@/store/workspace-events'

import { useGatewayRequest } from '../gateway/hooks/use-gateway-request'
import { $specsWorkspace, ProjectPicker } from '../project-picker'

import {
  approveCommand,
  createCommand,
  currentStage,
  isStartable,
  latestRunBySpec,
  nextAction,
  refineCommand,
  resumeCommand,
  runAllCommand,
  SPEC_STEPS,
  type SpecCreateMode,
  type SpecDetail,
  type SpecRun,
  type SpecStage,
  type SpecStep,
  type SpecStepState,
  type SpecSummary,
  type SpecTask,
  startTaskCommand,
  stepStage,
  stepStates
} from './spec-model'

// Specs refresh on their own while open: the agent edits them in the
// background, and the page should follow without a manual reload.
const REFRESH_MS = 3000
// While an agent is working, its activity is polled faster.
const RUN_REFRESH_MS = 1000

export function SpecsView(props: React.ComponentProps<'section'>) {
  const { t } = useI18n()
  const s = t.specs
  const chatCwd = useStore($currentCwd).trim()
  const picked = useStore($specsWorkspace)
  // The picked project, else the one the current chat is in.
  const cwd = (picked ?? chatCwd).trim()
  const gatewayState = useStore($gatewayState)
  const tick = useStore($workspaceChangeTick)
  const { requestGateway } = useGatewayRequest()
  const queryClient = useQueryClient()
  const [selected, setSelected] = useState<null | string>(null)
  const [composerOpen, setComposerOpen] = useState(false)
  // Specs whose action is on its way to the backend — holds their buttons
  // for the round trip, before the run itself shows up.
  const [sending, setSending] = useState<Record<string, true>>({})
  const connected = gatewayState === 'open' && Boolean(cwd)

  const list = useQuery({
    queryKey: ['specs', cwd],
    queryFn: () => requestGateway<{ specs: SpecSummary[] }>('spec.list', { cwd }),
    enabled: connected,
    refetchInterval: REFRESH_MS
  })

  const runsQuery = useQuery({
    queryKey: ['spec-runs', cwd],
    queryFn: () => requestGateway<{ runs: SpecRun[] }>('spec.runs', { cwd }),
    enabled: connected,
    refetchInterval: query =>
      query.state.data?.runs.some(run => run.status === 'running') ? RUN_REFRESH_MS : REFRESH_MS
  })

  const specs = list.data?.specs ?? []
  const active = specs.find(spec => spec.name === selected) ?? specs[0]
  const latestRuns = latestRunBySpec(runsQuery.data?.runs ?? [])

  const detail = useQuery({
    queryKey: ['spec', cwd, active?.name],
    queryFn: () => requestGateway<SpecDetail>('spec.get', { cwd, name: active!.name }),
    enabled: connected && Boolean(active),
    // Keep painting the previous spec while the next loads, instead of
    // dropping the panel to a placeholder and remounting it.
    placeholderData: keepPreviousData,
    refetchInterval: REFRESH_MS
  })

  // A file-mutating tool just finished somewhere — re-read now, not in 3s.
  const { refetch: refetchList } = list
  const { refetch: refetchDetail } = detail

  useEffect(() => {
    if (tick > 0) {
      void refetchList()
      void refetchDetail()
    }
  }, [tick, refetchList, refetchDetail])

  // The agent writes the spec's files in the background; while one is
  // running, follow its edits at the run's pace.
  const anyRunning = Object.values(latestRuns).some(run => run.status === 'running')

  useEffect(() => {
    if (!anyRunning) {
      return
    }

    const timer = window.setInterval(() => {
      void refetchList()
      void refetchDetail()
    }, RUN_REFRESH_MS * 2)

    return () => window.clearInterval(timer)
  }, [anyRunning, refetchList, refetchDetail])

  // Every action runs here, headlessly — no chat is opened and the page stays.
  const send = async (args: string, specName?: string) => {
    if (specName) {
      setSending(current => ({ ...current, [specName]: true }))
    }

    try {
      const result = await requestGateway<SpecRunResult>('spec.run', {
        args,
        cwd,
        session_id: $activeSessionId.get() ?? undefined
      })

      if (result.spec) {
        setSelected(result.spec)
      }

      if (!result.run && result.output) {
        notify({ kind: 'info', title: s.title, message: result.output })
      }

      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['spec-runs', cwd] }),
        queryClient.invalidateQueries({ queryKey: ['specs', cwd] })
      ])
    } catch (error) {
      notifyError(error, s.startFailed)
    } finally {
      if (specName) {
        setSending(({ [specName]: _done, ...rest }) => rest)
      }
    }
  }

  const stop = async (runId: string) => {
    try {
      await requestGateway('spec.stop', { run_id: runId })
      await queryClient.invalidateQueries({ queryKey: ['spec-runs', cwd] })
    } catch (error) {
      notifyError(error, s.stopFailed)
    }
  }

  const create = (mode: SpecCreateMode, feature: string) => {
    setComposerOpen(false)
    void send(createCommand(mode, feature))
  }

  const busy = (name: string) => Boolean(sending[name]) || latestRuns[name]?.status === 'running'
  const shownDetail = detail.data && active ? detail.data : undefined

  let body: ReactNode

  if (!cwd) {
    body = (
      <PageNotice icon="folder-opened" text={s.noProjectBody} title={s.noProjectTitle}>
        <ProjectPicker chatCwd={chatCwd} onChange={path => $specsWorkspace.set(path)} value="" />
      </PageNotice>
    )
  } else if (!list.data && list.isError) {
    // Only a load that never succeeded is an error page; a failed refresh
    // keeps showing what we already have.
    body = (
      <PageNotice icon="warning" text={String(list.error)} title={s.loadFailed}>
        <Button onClick={() => void list.refetch()} size="sm" variant="secondary">
          {s.retry}
        </Button>
      </PageNotice>
    )
  } else if (!list.data) {
    body = <SpecsSkeleton />
  } else if (specs.length === 0) {
    body = <Welcome disabled={!connected} onCreate={create} />
  } else {
    body = (
      <div className="grid gap-5">
        {composerOpen && <NewSpec disabled={!connected} onCancel={() => setComposerOpen(false)} onCreate={create} />}
        <div className="grid gap-5 lg:grid-cols-[15rem_minmax(0,1fr)] lg:items-start">
          <SpecList activeName={active?.name} busy={busy} onSelect={setSelected} specs={specs} />
          {shownDetail ? (
            <SpecPanel
              cwd={cwd}
              key={shownDetail.name}
              onSend={args => void send(args, shownDetail.name)}
              onStop={runId => void stop(runId)}
              pending={busy(shownDetail.name)}
              run={latestRuns[shownDetail.name]}
              spec={shownDetail}
            />
          ) : (
            <PanelSkeleton />
          )}
        </div>
      </div>
    )
  }

  return (
    <section
      {...props}
      className="flex h-full min-w-0 flex-col overflow-hidden bg-(--ui-chat-surface-background)"
      data-testid="specs-view"
    >
      <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
        <div className="mx-auto grid w-full max-w-6xl gap-4 px-4 pb-8 pt-[calc(var(--titlebar-height,34px)+0.75rem)] sm:px-6">
          <header className="flex flex-wrap items-end justify-between gap-4">
            <div className="grid max-w-2xl gap-1">
              <h1 className="text-xl font-semibold tracking-tight text-(--ui-text-primary)">{s.title}</h1>
              <p className="text-sm leading-5 text-(--ui-text-secondary)">{s.subtitle}</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {cwd && <ProjectPicker chatCwd={chatCwd} onChange={path => $specsWorkspace.set(path)} value={cwd} />}
              {specs.length > 0 && !composerOpen && (
                <Button disabled={!connected} onClick={() => setComposerOpen(true)} size="sm">
                  <Codicon name="add" size="0.85rem" />
                  {s.newSpec}
                </Button>
              )}
            </div>
          </header>
          {body}
        </div>
      </div>
    </section>
  )
}

interface SpecRunResult {
  output: string
  run: null | SpecRun
  spec: string
}

function PageNotice({
  children,
  icon,
  text,
  title
}: {
  children?: ReactNode
  icon: string
  text: string
  title: string
}) {
  return (
    <div className="grid place-items-center rounded-xl border border-dashed border-(--ui-stroke-tertiary) px-6 py-16 text-center">
      <div className="grid max-w-sm justify-items-center gap-2">
        <Codicon className="text-(--ui-text-tertiary)" name={icon} size="1.5rem" />
        <h2 className="text-sm font-semibold text-(--ui-text-primary)">{title}</h2>
        <p className="text-xs leading-5 text-(--ui-text-tertiary)">{text}</p>
        {children}
      </div>
    </div>
  )
}

function SpecsSkeleton() {
  return (
    <div aria-busy="true" className="grid gap-5 lg:grid-cols-[15rem_minmax(0,1fr)]">
      <div className="grid content-start gap-2">
        <Skeleton className="h-14 rounded-lg" />
        <Skeleton className="h-14 rounded-lg" />
      </div>
      <PanelSkeleton />
    </div>
  )
}

function PanelSkeleton() {
  return (
    <div aria-busy="true" className="grid gap-4 rounded-xl border border-(--ui-stroke-tertiary) p-5">
      <Skeleton className="h-6 w-48" />
      <Skeleton className="h-12 rounded-lg" />
      <Skeleton className="h-40 rounded-lg" />
    </div>
  )
}

const CREATE_MODES = ['step', 'quick', 'auto'] as const

// Borderless writing surface: the card around it is the field's frame.
const BARE_TEXTAREA =
  'block min-h-24 w-full resize-none bg-transparent text-sm leading-6 text-(--ui-text-primary) outline-none placeholder:text-(--ui-text-quaternary)'

/** First spec in a project: what the workflow is, and where to start it. */
function Welcome({
  disabled,
  onCreate
}: {
  disabled: boolean
  onCreate: (mode: SpecCreateMode, feature: string) => void
}) {
  const { t } = useI18n()
  const s = t.specs

  return (
    <div className="grid justify-items-center gap-8 rounded-xl border border-(--ui-stroke-tertiary) px-6 py-10">
      <div className="grid max-w-xl justify-items-center gap-2 text-center">
        <span className="grid size-10 place-items-center rounded-xl bg-(--ui-bg-tertiary) text-(--ui-text-secondary)">
          <Codicon name="checklist" size="1.25rem" />
        </span>
        <h2 className="text-lg font-semibold tracking-tight text-(--ui-text-primary)">{s.welcomeTitle}</h2>
        <p className="text-sm leading-6 text-(--ui-text-secondary)">{s.welcomeBody}</p>
      </div>
      <ol className="grid w-full max-w-2xl grid-cols-2 gap-2 sm:grid-cols-4">
        {SPEC_STEPS.map((step, index) => (
          <li className="grid gap-1 rounded-lg bg-(--ui-bg-tertiary)/50 px-3 py-2.5" key={step}>
            <span className="text-[0.66rem] font-medium text-(--ui-text-quaternary)">{index + 1}</span>
            <span className="text-xs font-medium text-(--ui-text-primary)">{s.steps[step]}</span>
            <span className="text-[0.68rem] leading-4 text-(--ui-text-tertiary)">{s.stepHints[step]}</span>
          </li>
        ))}
      </ol>
      <div className="w-full max-w-2xl">
        <NewSpec disabled={disabled} onCreate={onCreate} />
      </div>
    </div>
  )
}

function NewSpec({
  disabled,
  onCancel,
  onCreate
}: {
  disabled: boolean
  onCancel?: () => void
  onCreate: (mode: SpecCreateMode, feature: string) => void
}) {
  const { t } = useI18n()
  const s = t.specs
  const [feature, setFeature] = useState('')
  const [mode, setMode] = useState<SpecCreateMode>('step')
  const canCreate = !disabled && feature.trim().length > 0

  const submit = () => {
    if (canCreate) {
      onCreate(mode, feature)
      setFeature('')
    }
  }

  return (
    <section className="grid gap-3 rounded-xl border border-(--ui-stroke-tertiary) bg-(--ui-bg-tertiary)/30 p-4">
      <textarea
        aria-label={s.newTitle}
        autoFocus={Boolean(onCancel)}
        className={BARE_TEXTAREA}
        onChange={event => setFeature(event.target.value)}
        onKeyDown={event => {
          if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
            event.preventDefault()
            submit()
          }
        }}
        placeholder={s.newPlaceholder}
        value={feature}
      />
      <div className="flex flex-wrap items-center gap-3 border-t border-(--ui-stroke-tertiary) pt-3">
        <SegmentedControl
          onChange={setMode}
          options={CREATE_MODES.map(id => ({ id, label: s.modes[id].label }))}
          value={mode}
        />
        <p className="min-w-0 flex-1 text-[0.7rem] leading-4 text-(--ui-text-tertiary)">{s.modes[mode].hint}</p>
        {onCancel && (
          <Button onClick={onCancel} size="sm" variant="ghost">
            {s.cancel}
          </Button>
        )}
        <Button disabled={!canCreate} onClick={submit} size="sm">
          {s.create}
        </Button>
      </div>
    </section>
  )
}

interface SpecListProps {
  activeName: string | undefined
  onSelect: (name: string) => void
  busy: (name: string) => boolean
  specs: SpecSummary[]
}

function SpecList({ activeName, busy, onSelect, specs }: SpecListProps) {
  const { t } = useI18n()
  const s = t.specs

  return (
    <nav aria-label={s.listTitle} className="grid content-start gap-1.5">
      <h2 className="px-1 text-[0.66rem] font-semibold uppercase tracking-[0.07em] text-(--ui-text-quaternary)">
        {s.listTitle}
      </h2>
      <ul className="grid gap-1">
        {specs.map(spec => {
          const isActive = spec.name === activeName
          const { completed, total } = spec.progress

          return (
            <li key={spec.name}>
              <button
                aria-current={isActive ? 'true' : undefined}
                className={cn(
                  'grid w-full gap-1.5 rounded-lg border px-3 py-2.5 text-left transition-colors',
                  isActive
                    ? 'border-(--ui-stroke-secondary) bg-(--ui-bg-tertiary)'
                    : 'border-transparent hover:bg-(--ui-bg-tertiary)/60'
                )}
                data-testid="spec-list-item"
                onClick={() => onSelect(spec.name)}
                type="button"
              >
                <span className="flex min-w-0 items-center gap-2">
                  <span className="min-w-0 flex-1 truncate text-[0.8rem] font-medium text-(--ui-text-primary)">
                    {spec.name}
                  </span>
                  {busy(spec.name) && <GlyphSpinner ariaLabel={s.working} className="shrink-0" spinner="breathe" />}
                </span>
                <span className="flex items-center gap-2 text-[0.66rem] text-(--ui-text-tertiary)">
                  <PhaseChip phase={spec.phase} />
                  {spec.documents.tasks && <span>{s.tasksProgress(completed, total)}</span>}
                </span>
                {spec.documents.tasks && total > 0 && <ProgressBar value={completed / total} />}
              </button>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}

function ProgressBar({ value }: { value: number }) {
  return (
    <span className="block h-1 overflow-hidden rounded-full bg-(--ui-bg-tertiary)">
      <span
        className="block h-full rounded-full bg-emerald-500/80 transition-[width] duration-500"
        style={{ width: `${Math.round(Math.min(1, Math.max(0, value)) * 100)}%` }}
      />
    </span>
  )
}

const PHASE_TONE: Record<SpecSummary['phase'], string> = {
  design: 'bg-sky-500/12 text-sky-700 dark:text-sky-300',
  done: 'bg-emerald-500/12 text-emerald-700 dark:text-emerald-300',
  implementation: 'bg-amber-500/14 text-amber-700 dark:text-amber-300',
  requirements: 'bg-violet-500/12 text-violet-700 dark:text-violet-300',
  tasks: 'bg-(--ui-bg-tertiary) text-(--ui-text-secondary)'
}

function PhaseChip({ phase }: { phase: SpecSummary['phase'] }) {
  const { t } = useI18n()

  return (
    <span
      className={cn('rounded-full px-1.5 py-px text-[0.6rem] font-medium', PHASE_TONE[phase])}
      data-testid="spec-phase"
    >
      {t.specs.phase[phase]}
    </span>
  )
}

interface SpecPanelProps {
  cwd: string
  onSend: (command: string) => void
  onStop: (runId: string) => void
  pending: boolean
  /** The newest agent run for this spec, if any — live or finished. */
  run?: SpecRun
  spec: SpecDetail
}

function SpecPanel({ cwd, onSend, onStop, pending, run, spec }: SpecPanelProps) {
  const { t } = useI18n()
  const s = t.specs
  const newest = currentStage(spec)
  const [tab, setTab] = useState<SpecStage>(newest)

  // A newly written document comes to the front (approving the design lands
  // you on the task list once it exists).
  useEffect(() => setTab(newest), [newest])

  const openFile = async (path: string) => {
    try {
      const target = await normalizeOrLocalPreviewTarget(path, cwd)

      if (target) {
        openPreview(target, 'file-browser')
      }
    } catch (error) {
      notifyError(error, s.openFailed)
    }
  }

  return (
    <article
      className="grid min-w-0 gap-5 rounded-xl border border-(--ui-stroke-tertiary) p-5"
      data-testid="spec-panel"
    >
      <header className="grid gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="truncate text-base font-semibold tracking-tight text-(--ui-text-primary)">{spec.name}</h2>
          <PhaseChip phase={spec.phase} />
          {spec.legacy && <span className="text-[0.66rem] text-(--ui-text-quaternary)">{s.legacy}</span>}
        </div>
        <p className="truncate font-mono text-[0.66rem] text-(--ui-text-quaternary)" title={spec.path}>
          {spec.path}
        </p>
      </header>

      <Stepper active={tab} onSelect={setTab} running={pending} spec={spec} />

      {run && (
        <RunCard
          onRetry={run.retry_args && !pending ? () => onSend(run.retry_args) : undefined}
          onStop={() => onStop(run.id)}
          run={run}
        />
      )}

      {!pending && <NextStep onSend={onSend} onShow={setTab} spec={spec} />}

      <div role="tabpanel">
        {tab === 'tasks' && spec.documents.tasks ? (
          <TaskList onOpen={() => void openFile(spec.files.tasks)} onSend={onSend} pending={pending} spec={spec} />
        ) : (
          <DocumentView
            onOpen={() => void openFile(spec.files[tab])}
            onSend={onSend}
            pending={pending}
            spec={spec}
            stage={tab}
          />
        )}
      </div>
    </article>
  )
}

/** The workflow as four connected steps; the first three open their document. */
function Stepper({
  active,
  onSelect,
  running,
  spec
}: {
  active: SpecStage
  onSelect: (stage: SpecStage) => void
  running: boolean
  spec: SpecDetail
}) {
  const { t } = useI18n()
  const s = t.specs
  const states = stepStates(spec, running)

  const stateLabel = (step: SpecStep, state: SpecStepState) =>
    step === 'build' && state !== 'upcoming'
      ? s.tasksProgress(spec.progress.completed, spec.progress.total)
      : s.stepState[state]

  return (
    <div aria-label={s.title} className="grid grid-cols-4 gap-1.5" role="tablist">
      {SPEC_STEPS.map((step, index) => {
        const state = states[step]
        const stage = stepStage(step)
        // The build step shows the task list too, but only one of the two
        // reads as selected.
        const selected = step !== 'build' && active === stage

        return (
          <button
            aria-selected={selected}
            className={cn(
              'grid min-w-0 gap-1.5 rounded-lg px-2.5 pb-2 pt-1.5 text-left transition-colors',
              selected ? 'bg-(--ui-bg-tertiary)' : 'hover:bg-(--ui-bg-tertiary)/50'
            )}
            data-state={state}
            key={step}
            onClick={() => onSelect(stage)}
            role="tab"
            type="button"
          >
            <span
              className={cn(
                'h-0.5 rounded-full',
                state === 'done'
                  ? 'bg-emerald-500/80'
                  : state === 'review'
                    ? 'bg-violet-500/80'
                    : state === 'drafting'
                      ? 'animate-pulse bg-(--ui-text-tertiary)'
                      : 'bg-(--ui-stroke-tertiary)'
              )}
            />
            <span className="flex min-w-0 items-center gap-1.5">
              <StepGlyph index={index} state={state} />
              <span className="truncate text-xs font-medium text-(--ui-text-primary)">{s.steps[step]}</span>
            </span>
            <span className="truncate text-[0.64rem] text-(--ui-text-tertiary)">{stateLabel(step, state)}</span>
          </button>
        )
      })}
    </div>
  )
}

function StepGlyph({ index, state }: { index: number; state: SpecStepState }) {
  if (state === 'done') {
    return <Codicon className="shrink-0 text-emerald-600 dark:text-emerald-400" name="pass-filled" size="0.85rem" />
  }

  return (
    <span
      className={cn(
        'grid size-3.5 shrink-0 place-items-center rounded-full text-[0.55rem] font-semibold',
        state === 'review'
          ? 'bg-violet-500/80 text-white'
          : 'bg-(--ui-bg-tertiary) text-(--ui-text-tertiary) ring-1 ring-(--ui-stroke-tertiary)'
      )}
    >
      {index + 1}
    </span>
  )
}

function NextStep({
  onSend,
  onShow,
  spec
}: {
  onSend: (command: string) => void
  onShow: (stage: SpecStage) => void
  spec: SpecDetail
}) {
  const { t } = useI18n()
  const s = t.specs
  const action = nextAction(spec)

  let text = s.next[spec.phase]
  let button: ReactNode = null

  if (action.kind === 'approve') {
    text = s.next[action.stage]
    button = (
      <Button onClick={() => onSend(approveCommand(spec.name, action.stage))} size="sm">
        {s.approve[action.stage as 'design' | 'requirements']}
      </Button>
    )
  } else if (action.kind === 'start') {
    const task = spec.tasks.find(item => item.id === action.taskId)

    button = (
      <Button
        className="max-w-72"
        onClick={() => {
          onShow('tasks')
          onSend(startTaskCommand(spec.name, action.taskId))
        }}
        size="sm"
      >
        <Codicon name="play" size="0.75rem" />
        <span className="truncate">{s.startNext(action.taskId, task?.title ?? '')}</span>
      </Button>
    )
  } else if (action.kind === 'wait') {
    // Nothing is running (the bar only shows then): the draft was stopped or
    // failed, so offer to write it rather than claiming it's being written.
    text = s.requirementsMissing
    button = (
      <Button onClick={() => onSend(resumeCommand(spec.name))} size="sm">
        <Codicon name="edit" size="0.75rem" />
        {s.writeRequirements}
      </Button>
    )
  }

  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-3 rounded-lg px-3.5 py-2.5',
        'bg-violet-500/8 ring-1 ring-violet-500/15'
      )}
      data-testid="spec-next-step"
    >
      <Codicon
        className="shrink-0 text-violet-600 dark:text-violet-300"
        name={action.kind === 'done' ? 'pass' : action.kind === 'wait' ? 'info' : 'arrow-right'}
        size="0.95rem"
      />
      <p className="min-w-0 flex-1 text-xs leading-5 text-(--ui-text-secondary)">{text}</p>
      {button}
    </div>
  )
}

interface DocumentViewProps {
  onOpen: () => void
  onSend: (command: string) => void
  pending: boolean
  spec: SpecDetail
  stage: SpecStage
}

function DocumentView({ onOpen, onSend, pending, spec, stage }: DocumentViewProps) {
  const { t } = useI18n()
  const s = t.specs
  const [changes, setChanges] = useState<null | string>(null)

  if (!spec.documents[stage]) {
    return (
      <div className="grid place-items-center rounded-lg border border-dashed border-(--ui-stroke-tertiary) px-6 py-12 text-center">
        <p className="max-w-sm text-xs leading-5 text-(--ui-text-tertiary)">
          {stage === 'requirements' && !pending ? s.requirementsMissing : s.notWritten[stage]}
        </p>
      </div>
    )
  }

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          disabled={pending}
          onClick={() => setChanges(changes === null ? '' : null)}
          size="sm"
          variant="secondary"
        >
          {s.requestChanges}
        </Button>
        <Button className="ml-auto" onClick={onOpen} size="sm" variant="ghost">
          <Codicon name="go-to-file" size="0.8rem" />
          {s.openFile}
        </Button>
      </div>
      {changes !== null && (
        <div className="grid gap-2 rounded-lg border border-(--ui-stroke-tertiary) p-3">
          <textarea
            aria-label={s.requestChanges}
            autoFocus
            className={cn(BARE_TEXTAREA, 'min-h-20')}
            onChange={event => setChanges(event.target.value)}
            placeholder={s.changesPlaceholder}
            value={changes}
          />
          <div className="flex justify-end gap-2">
            <Button onClick={() => setChanges(null)} size="sm" variant="ghost">
              {s.cancel}
            </Button>
            <Button
              disabled={!changes.trim()}
              onClick={() => {
                onSend(refineCommand(spec.name, stage, changes))
                setChanges(null)
              }}
              size="sm"
            >
              {s.sendChanges}
            </Button>
          </div>
        </div>
      )}
      <div
        className="max-h-[60vh] overflow-y-auto rounded-lg bg-(--ui-bg-tertiary)/25 px-5 py-4"
        data-testid={`spec-doc-${stage}`}
      >
        <CompactMarkdown className="text-[0.8rem] leading-6 text-(--ui-text-secondary)" text={spec.content[stage]} />
      </div>
    </div>
  )
}

const TASK_GLYPH: Record<SpecTask['status'], { icon: string; tone: string }> = {
  completed: { icon: 'pass-filled', tone: 'text-emerald-600 dark:text-emerald-400' },
  in_progress: { icon: 'circle-large-filled', tone: 'text-amber-500 animate-pulse' },
  not_started: { icon: 'circle-large', tone: 'text-(--ui-text-quaternary)' },
  queued: { icon: 'history', tone: 'text-sky-500' }
}

function TaskList({
  onOpen,
  onSend,
  pending,
  spec
}: {
  onOpen: () => void
  onSend: (command: string) => void
  pending: boolean
  spec: SpecDetail
}) {
  const { t } = useI18n()
  const s = t.specs
  const [includeOptional, setIncludeOptional] = useState(false)
  const { completed, total } = spec.progress

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <Button
          disabled={pending || (!spec.next_task && !includeOptional)}
          onClick={() => onSend(runAllCommand(spec.name, includeOptional))}
          size="sm"
        >
          <Codicon name="run-all" size="0.8rem" />
          {s.runAll}
        </Button>
        <label className="flex items-center gap-1.5 text-xs text-(--ui-text-secondary)">
          <Checkbox checked={includeOptional} onCheckedChange={value => setIncludeOptional(value === true)} />
          {s.includeOptional}
        </label>
        <Button className="ml-auto" onClick={onOpen} size="sm" variant="ghost">
          <Codicon name="go-to-file" size="0.8rem" />
          {s.openFile}
        </Button>
      </div>
      <div className="grid gap-1.5">
        <div className="flex items-center justify-between text-[0.7rem] text-(--ui-text-tertiary)">
          <span>{s.tasksProgress(completed, total)}</span>
          <span>{total ? Math.round((completed / total) * 100) : 0}%</span>
        </div>
        <ProgressBar value={total ? completed / total : 0} />
      </div>
      <ol
        className="grid gap-px overflow-hidden rounded-lg border border-(--ui-stroke-tertiary)"
        data-testid="spec-tasks"
      >
        {spec.tasks.map(task => {
          const glyph = TASK_GLYPH[task.status]
          const isNext = task.id === spec.next_task

          return (
            <li
              className={cn(
                'group grid grid-cols-[1rem_minmax(0,1fr)_auto] items-start gap-2.5 bg-(--ui-chat-surface-background) px-3 py-2.5 hover:bg-(--ui-bg-tertiary)/40',
                task.depth > 0 && 'pl-9',
                isNext && 'bg-violet-500/5'
              )}
              data-status={task.status}
              data-task={task.id}
              data-testid="spec-task"
              key={`${task.id}-${task.line}`}
            >
              <Codicon
                aria-label={s.taskStatus[task.status]}
                className={cn('mt-0.5', glyph.tone)}
                name={glyph.icon}
                size="0.9rem"
              />
              <div className="grid min-w-0 gap-0.5">
                <span
                  className={cn(
                    'text-[0.8rem] leading-5',
                    task.status === 'completed'
                      ? 'text-(--ui-text-tertiary) line-through decoration-(--ui-text-quaternary)'
                      : 'text-(--ui-text-primary)'
                  )}
                >
                  <span className="mr-1.5 font-mono text-(--ui-text-tertiary)">{task.id}</span>
                  {task.title}
                  {task.optional && (
                    <span className="ml-1.5 rounded-sm bg-(--ui-bg-tertiary) px-1 text-[0.6rem] text-(--ui-text-tertiary)">
                      {s.optional}
                    </span>
                  )}
                </span>
                {task.details.length > 0 && (
                  <ul className="grid gap-px text-[0.7rem] leading-4 text-(--ui-text-tertiary)">
                    {task.details.map((line, i) => (
                      <li key={i}>{line}</li>
                    ))}
                  </ul>
                )}
                {task.requirements.length > 0 && (
                  <span className="text-[0.66rem] text-(--ui-text-quaternary)">
                    {s.requirementsRef(task.requirements.join(', '))}
                  </span>
                )}
              </div>
              {isStartable(task) && (
                <Button
                  className={cn(
                    'h-6 px-2 text-[0.68rem]',
                    !isNext && 'opacity-0 group-hover:opacity-100 focus-visible:opacity-100'
                  )}
                  disabled={pending}
                  onClick={() => onSend(startTaskCommand(spec.name, task.id))}
                  size="sm"
                  variant={isNext ? 'secondary' : 'ghost'}
                >
                  <Codicon name="play" size="0.75rem" />
                  {s.startTask}
                </Button>
              )}
            </li>
          )
        })}
      </ol>
      <p className="text-[0.68rem] text-(--ui-text-quaternary)">{s.runsInBackground}</p>
    </div>
  )
}

const RUN_TONE: Record<SpecRun['status'], string> = {
  completed: 'text-emerald-600 dark:text-emerald-400',
  failed: 'text-destructive',
  interrupted: 'text-(--ui-text-tertiary)',
  running: 'text-(--ui-text-secondary)'
}

const RUN_ICON: Record<Exclude<SpecRun['status'], 'running'>, string> = {
  completed: 'pass-filled',
  failed: 'error',
  interrupted: 'debug-stop'
}

/** The agent's work on this spec, shown in place: live activity while it
 *  runs, then its reply (usually the review question for the next phase). */
function RunCard({ onRetry, onStop, run }: { onRetry?: () => void; onStop: () => void; run: SpecRun }) {
  const { t } = useI18n()
  const s = t.specs
  const running = run.status === 'running'
  const elapsed = useElapsedSeconds(running, `spec-run:${run.id}`, run.started_at * 1000)
  const recent = run.activity.slice(-6)
  const reply = run.summary
  const unfinished = run.status === 'interrupted' || run.status === 'failed'

  return (
    <section
      className={cn(
        'grid gap-2 rounded-lg px-3.5 py-3',
        running ? 'bg-(--ui-bg-tertiary)/55 ring-1 ring-(--ui-stroke-tertiary)' : 'bg-(--ui-bg-tertiary)/35'
      )}
      data-status={run.status}
      data-testid="spec-run"
    >
      <header className="flex min-w-0 items-center gap-2">
        {running ? (
          <GlyphSpinner ariaLabel={s.runStatus.running} className="shrink-0" spinner="breathe" />
        ) : (
          <Codicon
            className={cn('shrink-0', RUN_TONE[run.status])}
            name={RUN_ICON[run.status as Exclude<SpecRun['status'], 'running'>]}
            size="0.9rem"
          />
        )}
        <span className="min-w-0 flex-1 truncate text-xs font-medium text-(--ui-text-primary)" title={run.label}>
          {run.label}
        </span>
        <span className={cn('shrink-0 text-[0.66rem]', RUN_TONE[run.status])}>{s.runStatus[run.status]}</span>
        {running && <ActivityTimerText seconds={elapsed} />}
        {unfinished && onRetry && (
          <Button className="h-6 px-2 text-[0.66rem]" onClick={onRetry} size="sm" variant="secondary">
            <Codicon name="refresh" size="0.7rem" />
            {s.retry}
          </Button>
        )}
        {running && (
          <Button className="h-6 px-2 text-[0.66rem]" onClick={onStop} size="sm" variant="ghost">
            <Codicon name="debug-stop" size="0.7rem" />
            {s.stop}
          </Button>
        )}
      </header>
      {running ? (
        <ol className="grid gap-0.5 pl-6" data-testid="spec-run-activity">
          {recent.length === 0 && <li className="text-[0.68rem] text-(--ui-text-quaternary)">{s.working}</li>}
          {recent.map((line, index) => (
            <li
              className={cn(
                'truncate font-mono text-[0.66rem] leading-5',
                index === recent.length - 1 ? 'text-(--ui-text-secondary)' : 'text-(--ui-text-quaternary)'
              )}
              key={`${line.at}-${index}`}
              title={line.text}
            >
              {line.text}
            </li>
          ))}
        </ol>
      ) : run.status === 'failed' ? (
        <p className="pl-6 text-[0.72rem] leading-5 text-destructive" data-testid="spec-run-error">
          {run.error || s.runFailedNote}
        </p>
      ) : run.status === 'interrupted' && !reply ? (
        <p className="pl-6 text-[0.72rem] leading-5 text-(--ui-text-tertiary)">{s.stoppedNote}</p>
      ) : (
        reply && (
          <div className="max-h-56 overflow-y-auto pl-6" data-testid="spec-run-reply">
            <CompactMarkdown className="text-[0.76rem] leading-5 text-(--ui-text-secondary)" text={reply} />
          </div>
        )
      )}
    </section>
  )
}
