import { useStore } from '@nanostores/react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { formatElapsed } from '@/components/chat/activity-timer'
import { Button } from '@/components/ui/button'
import { Codicon } from '@/components/ui/codicon'
import { GlyphSpinner } from '@/components/ui/glyph-spinner'
import { useI18n } from '@/i18n'
import { cn } from '@/lib/utils'
import { notifyError } from '@/store/notifications'
import { $activeSessionId, $currentCwd, $gatewayState } from '@/store/session'

import { useGatewayRequest } from '../gateway/hooks/use-gateway-request'

import { FlowRunView, RunStatusChip } from './flow-panel'
import { type HeadlessRun, toFlowRun, toSubagents } from './headless-runs'
import { $orchestratorWorkspace, ProjectPicker } from './project-picker'

// A running flow is polled briskly so its agents read as live; otherwise the
// list only needs to notice runs finishing.
const LIVE_REFRESH_MS = 1000
const IDLE_REFRESH_MS = 4000

const runsKey = (cwd: string) => ['orchestrator-runs', cwd] as const

/** Run the team on a task right here — no chat — and watch it work. */
export function RunsPanel() {
  const { t } = useI18n()
  const o = t.orchestrator
  const chatCwd = useStore($currentCwd).trim()
  const picked = useStore($orchestratorWorkspace)
  // The picked project, else the one the current chat is in.
  const cwd = (picked ?? chatCwd).trim()
  const gatewayState = useStore($gatewayState)
  const { requestGateway } = useGatewayRequest()
  const queryClient = useQueryClient()
  const [task, setTask] = useState('')
  const [starting, setStarting] = useState(false)
  const [selected, setSelected] = useState<null | string>(null)
  const connected = gatewayState === 'open' && Boolean(cwd)

  const runsQuery = useQuery({
    queryKey: runsKey(cwd),
    queryFn: () => requestGateway<{ runs: HeadlessRun[] }>('orchestrator.runs', { cwd }),
    enabled: connected,
    refetchInterval: query =>
      query.state.data?.runs.some(run => run.status === 'running') ? LIVE_REFRESH_MS : IDLE_REFRESH_MS
  })

  const runs = runsQuery.data?.runs ?? []
  const active = runs.find(run => run.id === selected) ?? runs[0]
  const anyRunning = runs.some(run => run.status === 'running')
  const canRun = connected && !starting && !anyRunning && task.trim().length > 0

  const start = async () => {
    if (!canRun) {
      return
    }

    setStarting(true)

    try {
      const { run } = await requestGateway<{ run: HeadlessRun }>('orchestrator.run', {
        cwd,
        session_id: $activeSessionId.get() ?? undefined,
        task: task.trim()
      })

      setSelected(run.id)
      setTask('')
      await queryClient.invalidateQueries({ queryKey: runsKey(cwd) })
    } catch (error) {
      notifyError(error, o.runFailed)
    } finally {
      setStarting(false)
    }
  }

  const stop = async (runId: string) => {
    try {
      await requestGateway('orchestrator.stop', { run_id: runId })
      await queryClient.invalidateQueries({ queryKey: runsKey(cwd) })
    } catch (error) {
      notifyError(error, o.stopFailed)
    }
  }

  if (!cwd) {
    return (
      <Notice icon="folder-opened" text={o.noProjectBody} title={o.noProjectTitle}>
        <ProjectPicker chatCwd={chatCwd} value="" />
      </Notice>
    )
  }

  return (
    <div className="grid gap-6">
      <section className="grid gap-3 rounded-xl border border-(--ui-stroke-tertiary) bg-(--ui-bg-tertiary)/30 p-4">
        <textarea
          aria-label={o.runTitle}
          className="block min-h-24 w-full resize-none bg-transparent text-sm leading-6 text-(--ui-text-primary) outline-none placeholder:text-(--ui-text-quaternary)"
          onChange={event => setTask(event.target.value)}
          onKeyDown={event => {
            if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
              event.preventDefault()
              void start()
            }
          }}
          placeholder={o.taskPlaceholder}
          value={task}
        />
        <div className="flex flex-wrap items-center gap-3 border-t border-(--ui-stroke-tertiary) pt-3">
          <ProjectPicker chatCwd={chatCwd} value={cwd} />
          <p className="min-w-0 flex-1 text-[0.7rem] leading-4 text-(--ui-text-tertiary)">
            {anyRunning ? o.oneAtATime : o.runsHere}
          </p>
          <Button disabled={!canRun} onClick={() => void start()} size="sm">
            <Codicon name="play" size="0.8rem" />
            {o.run}
          </Button>
        </div>
      </section>

      {runs.length === 0 ? (
        runsQuery.data && <Notice icon="organization" text={o.runsEmptyBody} title={o.runsEmptyTitle} />
      ) : (
        <div className="grid gap-5 lg:grid-cols-[15rem_minmax(0,1fr)] lg:items-start">
          <RunList activeId={active?.id} onSelect={setSelected} runs={runs} />
          {active && <RunDetail key={active.id} onStop={() => void stop(active.id)} run={active} />}
        </div>
      )}
    </div>
  )
}

function Notice({
  children,
  icon,
  text,
  title
}: {
  children?: React.ReactNode
  icon: string
  text: string
  title: string
}) {
  return (
    <div className="grid place-items-center rounded-xl border border-dashed border-(--ui-stroke-tertiary) px-6 py-14 text-center">
      <div className="grid max-w-sm justify-items-center gap-2">
        <Codicon className="text-(--ui-text-tertiary)" name={icon} size="1.5rem" />
        <h2 className="text-sm font-semibold text-(--ui-text-primary)">{title}</h2>
        <p className="text-xs leading-5 text-(--ui-text-tertiary)">{text}</p>
        {children && <div className="pt-2">{children}</div>}
      </div>
    </div>
  )
}

function duration(run: HeadlessRun): string {
  const end = run.finished_at ?? Date.now() / 1000

  return formatElapsed(Math.max(0, Math.round(end - run.started_at)))
}

function RunList({
  activeId,
  onSelect,
  runs
}: {
  activeId: string | undefined
  onSelect: (id: string) => void
  runs: HeadlessRun[]
}) {
  const { t } = useI18n()
  const o = t.orchestrator

  return (
    <nav aria-label={o.runsTitle} className="grid content-start gap-1.5">
      <h2 className="px-1 text-[0.66rem] font-semibold uppercase tracking-[0.07em] text-(--ui-text-quaternary)">
        {o.runsTitle}
      </h2>
      <ul className="grid gap-1">
        {runs.map(run => (
          <li key={run.id}>
            <button
              aria-current={run.id === activeId ? 'true' : undefined}
              className={cn(
                'grid w-full gap-1.5 rounded-lg border px-3 py-2.5 text-left transition-colors',
                run.id === activeId
                  ? 'border-(--ui-stroke-secondary) bg-(--ui-bg-tertiary)'
                  : 'border-transparent hover:bg-(--ui-bg-tertiary)/60'
              )}
              data-status={run.status}
              data-testid="orchestrator-run-item"
              onClick={() => onSelect(run.id)}
              type="button"
            >
              <span className="line-clamp-2 text-[0.78rem] leading-5 text-(--ui-text-primary)">{run.task}</span>
              <span className="flex items-center gap-2 text-[0.66rem] text-(--ui-text-tertiary)">
                <RunStatusChip status={run.status} />
                <span>{duration(run)}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  )
}

function RunDetail({ onStop, run }: { onStop: () => void; run: HeadlessRun }) {
  const { t } = useI18n()
  const o = t.orchestrator
  const flow = toFlowRun(run)
  const running = run.status === 'running'

  return (
    <article
      className="grid min-w-0 gap-3 rounded-xl border border-(--ui-stroke-tertiary) pt-3"
      data-status={run.status}
      data-testid="orchestrator-run"
    >
      <header className="flex min-w-0 items-start gap-3 px-4">
        <p className="min-w-0 flex-1 text-sm leading-5 text-(--ui-text-primary)">{run.task}</p>
        {running && (
          <Button className="h-7 shrink-0 px-2.5 text-xs" onClick={onStop} size="sm" variant="secondary">
            <Codicon name="debug-stop" size="0.75rem" />
            {o.stop}
          </Button>
        )}
      </header>
      {run.error && <p className="mx-4 rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">{run.error}</p>}
      {flow ? (
        <div className="flex min-w-0 flex-col px-1.5">
          <FlowRunView run={flow} showTask={false} subagents={toSubagents(run)} />
        </div>
      ) : (
        <div className="flex items-center gap-2 px-4 pb-4 text-xs text-(--ui-text-tertiary)">
          {running && <GlyphSpinner ariaLabel={o.starting} spinner="breathe" />}
          {running ? o.starting : o.noFlowRecorded}
        </div>
      )}
    </article>
  )
}
