import { useStore } from '@nanostores/react'
import { useQuery } from '@tanstack/react-query'
import { type ReactNode, useEffect, useState } from 'react'

import { CompactMarkdown } from '@/components/chat/compact-markdown'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Codicon } from '@/components/ui/codicon'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorState } from '@/components/ui/error-state'
import { FieldHint } from '@/components/ui/field'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { Textarea } from '@/components/ui/textarea'
import { useI18n } from '@/i18n'
import { normalizeOrLocalPreviewTarget } from '@/lib/local-preview'
import { cn } from '@/lib/utils'
import { $newChatRunAction } from '@/store/new-chat-run'
import { notifyError } from '@/store/notifications'
import { openPreview } from '@/store/preview'
import { $currentCwd, $gatewayState } from '@/store/session'
import { $workspaceChangeTick } from '@/store/workspace-events'

import { useGatewayRequest } from '../gateway/hooks/use-gateway-request'

import {
  approveCommand,
  canApprove,
  createCommand,
  currentStage,
  isStartable,
  nextAction,
  refineCommand,
  runAllCommand,
  SPEC_STAGES,
  type SpecCreateMode,
  type SpecDetail,
  type SpecStage,
  type SpecSummary,
  type SpecTask,
  startTaskCommand
} from './spec-model'

// Specs refresh on their own while open: the agent edits them from a chat, and
// the page should follow without a manual reload.
const REFRESH_MS = 3000

export function SpecsView(props: React.ComponentProps<'section'>) {
  const { t } = useI18n()
  const s = t.specs
  const cwd = useStore($currentCwd).trim()
  const gatewayState = useStore($gatewayState)
  const tick = useStore($workspaceChangeTick)
  const { requestGateway } = useGatewayRequest()
  const run = useStore($newChatRunAction)
  const [selected, setSelected] = useState<null | string>(null)

  const list = useQuery({
    queryKey: ['specs', cwd],
    queryFn: () => requestGateway<{ specs: SpecSummary[] }>('spec.list', { cwd }),
    enabled: gatewayState === 'open' && Boolean(cwd),
    refetchInterval: REFRESH_MS
  })

  const specs = list.data?.specs ?? []
  const active = specs.find(spec => spec.name === selected) ?? specs[0]

  const detail = useQuery({
    queryKey: ['spec', cwd, active?.name],
    queryFn: () => requestGateway<SpecDetail>('spec.get', { cwd, name: active!.name }),
    enabled: gatewayState === 'open' && Boolean(cwd && active),
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

  const send = (command: string) => run?.(command)

  return (
    <section
      {...props}
      className="flex h-full min-w-0 flex-col overflow-hidden bg-(--ui-chat-surface-background)"
      data-testid="specs-view"
    >
      <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
        <div className="mx-auto grid w-full max-w-5xl gap-6 px-6 pb-12 pt-[calc(var(--titlebar-height,34px)+1.5rem)]">
          <header className="grid gap-1.5">
            <h1 className="text-xl font-semibold tracking-tight text-(--ui-text-primary)">{s.title}</h1>
            <p className="max-w-3xl text-sm leading-5 text-(--ui-text-secondary)">{s.subtitle}</p>
          </header>

          {!cwd ? (
            <EmptyState description={s.noProjectBody} title={s.noProjectTitle} />
          ) : list.isError ? (
            <ErrorState description={String(list.error)} title={s.loadFailed}>
              <Button onClick={() => void list.refetch()} variant="secondary">
                {s.retry}
              </Button>
            </ErrorState>
          ) : (
            <div className="grid gap-6 lg:grid-cols-[17rem_minmax(0,1fr)] lg:items-start">
              <aside className="grid gap-5">
                <NewSpec disabled={!run} onCreate={(mode, feature) => send(createCommand(mode, feature))} />
                <SpecList activeName={active?.name} loading={list.isLoading} onSelect={setSelected} specs={specs} />
              </aside>
              <div className="min-w-0">
                {detail.data && active ? (
                  <SpecPanel cwd={cwd} key={detail.data.name} onSend={send} spec={detail.data} />
                ) : (
                  specs.length > 0 && <EmptyState title={s.select} />
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

const CREATE_MODES = ['step', 'quick', 'auto'] as const

function NewSpec({
  disabled,
  onCreate
}: {
  disabled: boolean
  onCreate: (mode: SpecCreateMode, feature: string) => void
}) {
  const { t } = useI18n()
  const s = t.specs
  const [feature, setFeature] = useState('')
  const [mode, setMode] = useState<SpecCreateMode>('step')

  return (
    <section className="grid gap-2 rounded-lg bg-(--ui-bg-tertiary)/45 p-3">
      <h2 className="text-sm font-semibold text-(--ui-text-primary)">{s.newTitle}</h2>
      <Textarea
        aria-label={s.newTitle}
        className="min-h-20 resize-y text-sm"
        onChange={event => setFeature(event.target.value)}
        placeholder={s.newPlaceholder}
        value={feature}
      />
      <SegmentedControl
        className="w-full"
        onChange={setMode}
        options={CREATE_MODES.map(id => ({ id, label: s.modes[id].label }))}
        value={mode}
      />
      <FieldHint>{s.modes[mode].hint}</FieldHint>
      <Button
        disabled={disabled || !feature.trim()}
        onClick={() => {
          onCreate(mode, feature)
          setFeature('')
        }}
      >
        {s.create}
      </Button>
    </section>
  )
}

interface SpecListProps {
  activeName: string | undefined
  loading: boolean
  onSelect: (name: string) => void
  specs: SpecSummary[]
}

function SpecList({ activeName, loading, onSelect, specs }: SpecListProps) {
  const { t } = useI18n()
  const s = t.specs

  return (
    <section className="grid gap-1.5">
      <h2 className="px-1 text-xs font-semibold uppercase tracking-[0.06em] text-(--ui-text-tertiary)">
        {s.listTitle}
      </h2>
      {!loading && specs.length === 0 && <p className="px-1 text-xs text-(--ui-text-tertiary)">{s.empty}</p>}
      <ul className="grid gap-0.5">
        {specs.map(spec => (
          <li key={spec.name}>
            <button
              aria-current={spec.name === activeName ? 'true' : undefined}
              className={cn(
                'grid w-full gap-0.5 rounded-md px-2.5 py-2 text-left transition-colors',
                spec.name === activeName ? 'bg-(--ui-bg-tertiary)' : 'hover:bg-(--ui-bg-tertiary)/60'
              )}
              data-testid="spec-list-item"
              onClick={() => onSelect(spec.name)}
              type="button"
            >
              <span className="truncate text-sm font-medium text-(--ui-text-primary)">{spec.name}</span>
              <span className="flex items-center gap-2 text-[0.68rem] text-(--ui-text-tertiary)">
                <PhaseChip phase={spec.phase} />
                {spec.documents.tasks && s.tasksProgress(spec.progress.completed, spec.progress.total)}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
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
  spec: SpecDetail
}

function SpecPanel({ cwd, onSend, spec }: SpecPanelProps) {
  const { t } = useI18n()
  const s = t.specs
  const newest = currentStage(spec)
  const [tab, setTab] = useState<SpecStage>(newest)

  // Like Kiro, a newly written document comes to the front (approving the
  // design lands you on the task list once it exists).
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
    <article className="grid gap-4" data-testid="spec-panel">
      <header className="grid gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-semibold tracking-tight text-(--ui-text-primary)">{spec.name}</h2>
          <PhaseChip phase={spec.phase} />
          {spec.legacy && <span className="text-[0.66rem] text-(--ui-text-quaternary)">{s.legacy}</span>}
        </div>
        <p className="truncate font-mono text-[0.68rem] text-(--ui-text-quaternary)" title={spec.path}>
          {spec.path}
        </p>
      </header>

      <NextStep onSend={onSend} onShow={setTab} spec={spec} />

      {/* Kiro's three spec tabs, in workflow order. */}
      <nav aria-label={s.title} className="flex gap-1 border-b border-(--ui-stroke-tertiary)" role="tablist">
        {SPEC_STAGES.map((stage, index) => (
          <button
            aria-selected={tab === stage}
            className={cn(
              '-mb-px flex items-center gap-1.5 border-b-2 px-3 py-2 text-xs font-medium transition-colors',
              tab === stage
                ? 'border-(--ui-text-primary) text-(--ui-text-primary)'
                : 'border-transparent text-(--ui-text-tertiary) hover:text-(--ui-text-secondary)'
            )}
            key={stage}
            onClick={() => setTab(stage)}
            role="tab"
            type="button"
          >
            <span
              className={cn(
                'grid size-4 place-items-center rounded-full text-[0.6rem]',
                spec.documents[stage]
                  ? 'bg-(--ui-text-primary) text-(--ui-chat-surface-background)'
                  : 'bg-(--ui-bg-tertiary) text-(--ui-text-tertiary)'
              )}
            >
              {index + 1}
            </span>
            {s.tabs[stage]}
          </button>
        ))}
      </nav>

      <div role="tabpanel">
        {tab === 'tasks' && spec.documents.tasks ? (
          <TaskList onOpen={() => void openFile(spec.files.tasks)} onSend={onSend} spec={spec} />
        ) : (
          <DocumentView onOpen={() => void openFile(spec.files[tab])} onSend={onSend} spec={spec} stage={tab} />
        )}
      </div>
    </article>
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
        onClick={() => {
          onShow('tasks')
          onSend(startTaskCommand(spec.name, action.taskId))
        }}
        size="sm"
      >
        {s.startNext(action.taskId, task?.title ?? '')}
      </Button>
    )
  } else if (action.kind === 'wait') {
    text = s.notWritten.requirements
  }

  return (
    <div
      className="flex flex-wrap items-center gap-3 rounded-lg bg-(--ui-bg-tertiary)/55 px-3.5 py-2.5"
      data-testid="spec-next-step"
    >
      <Codicon className="shrink-0 text-(--ui-text-tertiary)" name="debug-step-over" size="0.95rem" />
      <p className="min-w-0 flex-1 text-xs leading-5 text-(--ui-text-secondary)">{text}</p>
      {button}
    </div>
  )
}

interface DocumentViewProps {
  onOpen: () => void
  onSend: (command: string) => void
  spec: SpecDetail
  stage: SpecStage
}

function DocumentView({ onOpen, onSend, spec, stage }: DocumentViewProps) {
  const { t } = useI18n()
  const s = t.specs
  const [changes, setChanges] = useState<null | string>(null)

  if (!spec.documents[stage]) {
    return <p className="py-6 text-sm text-(--ui-text-tertiary)">{s.notWritten[stage]}</p>
  }

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        {canApprove(spec, stage) && (
          <Button onClick={() => onSend(approveCommand(spec.name, stage))} size="sm">
            {s.approve[stage as 'design' | 'requirements']}
          </Button>
        )}
        <Button onClick={() => setChanges(changes === null ? '' : null)} size="sm" variant="secondary">
          {s.requestChanges}
        </Button>
        <Button className="ml-auto" onClick={onOpen} size="sm" variant="ghost">
          <Codicon name="go-to-file" size="0.8rem" />
          {s.openFile}
        </Button>
      </div>
      {changes !== null && (
        <div className="grid gap-2">
          <Textarea
            aria-label={s.requestChanges}
            autoFocus
            className="min-h-20 text-sm"
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
      <div className="rounded-lg border border-(--ui-stroke-tertiary) px-5 py-4" data-testid={`spec-doc-${stage}`}>
        <CompactMarkdown className="text-[0.8rem] text-(--ui-text-secondary)" text={spec.content[stage]} />
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
  spec
}: {
  onOpen: () => void
  onSend: (command: string) => void
  spec: SpecDetail
}) {
  const { t } = useI18n()
  const s = t.specs
  const [includeOptional, setIncludeOptional] = useState(false)
  const { completed, total } = spec.progress
  const pct = total ? Math.round((completed / total) * 100) : 0

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <Button
          disabled={!spec.next_task && !includeOptional}
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
      <div className="grid gap-1">
        <div className="flex items-center justify-between text-[0.7rem] text-(--ui-text-tertiary)">
          <span>{s.tasksProgress(completed, total)}</span>
          <span>{pct}%</span>
        </div>
        <div className="h-1 overflow-hidden rounded-full bg-(--ui-bg-tertiary)">
          <div className="h-full rounded-full bg-emerald-500/80 transition-[width]" style={{ width: `${pct}%` }} />
        </div>
      </div>
      <ol className="grid gap-0.5" data-testid="spec-tasks">
        {spec.tasks.map(task => {
          const glyph = TASK_GLYPH[task.status]

          return (
            <li
              className={cn(
                'group grid grid-cols-[1rem_minmax(0,1fr)_auto] items-start gap-2.5 rounded-md px-2 py-1.5 hover:bg-(--ui-bg-tertiary)/50',
                task.depth > 0 && 'ml-6'
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
                    task.id !== spec.next_task && 'opacity-0 group-hover:opacity-100 focus-visible:opacity-100'
                  )}
                  onClick={() => onSend(startTaskCommand(spec.name, task.id))}
                  size="sm"
                  variant={task.id === spec.next_task ? 'secondary' : 'ghost'}
                >
                  <Codicon name="play" size="0.75rem" />
                  {s.startTask}
                </Button>
              )}
            </li>
          )
        })}
      </ol>
      <FieldHint>{s.runsInNewChat}</FieldHint>
    </div>
  )
}
