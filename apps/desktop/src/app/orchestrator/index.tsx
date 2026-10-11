import { useStore } from '@nanostores/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'

import { PageLoader } from '@/components/page-loader'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/ui/error-state'
import { FieldHint } from '@/components/ui/field'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { useI18n } from '@/i18n'
import { requestModelOptions } from '@/lib/model-options'
import { notifyError } from '@/store/notifications'
import { $activeGatewayProfile } from '@/store/profile'
import { $gatewayState } from '@/store/session'
import type { ModelOptionProvider } from '@/types/jettstui'

import { useGatewayRequest } from '../gateway/hooks/use-gateway-request'

import {
  AUTO_CHOICE,
  MAX_REVIEW_ROUNDS,
  orchestratePrompt,
  ORCHESTRATOR_ROLE_IDS,
  type OrchestratorAssignment,
  type OrchestratorConfig,
  type OrchestratorPayload,
  type OrchestratorRoleId,
  roleChoice,
  withReviewRounds,
  withRoleChoice
} from './flow-config'
import { $orchestratorRunAction } from './run-action'

const ROUND_OPTIONS = Array.from({ length: MAX_REVIEW_ROUNDS + 1 }, (_, n) => n)

export function OrchestratorView(props: React.ComponentProps<'section'>) {
  const { t } = useI18n()
  const { requestGateway } = useGatewayRequest()
  const run = useStore($orchestratorRunAction)
  const o = t.orchestrator
  const queryClient = useQueryClient()
  const gatewayState = useStore($gatewayState)
  const profile = useStore($activeGatewayProfile)
  const [task, setTask] = useState('')
  // Saves can overlap (quick successive picks); only the newest may publish
  // its server response, so an older reply never reverts a newer choice.
  const saveGeneration = useRef(0)

  const queryKey = ['orchestrator', (profile ?? '').trim() || 'default'] as const

  const flow = useQuery({
    queryKey,
    queryFn: () => requestGateway<OrchestratorPayload>('orchestrator.get'),
    enabled: gatewayState === 'open'
  })

  // Same catalog the cron model picker uses: configured providers only.
  const modelOptions = useQuery({
    queryKey: ['model-options', 'global'],
    queryFn: () => requestModelOptions({})
  })

  const save = useMutation({
    mutationFn: ({ config }: { config: OrchestratorConfig; generation: number }) =>
      requestGateway<OrchestratorPayload>('orchestrator.save', { config }),
    onMutate: ({ config }) => {
      const previous = queryClient.getQueryData<OrchestratorPayload>(queryKey)

      // Paint the choice immediately; the server's resolution lands after.
      queryClient.setQueryData<OrchestratorPayload>(queryKey, current => (current ? { ...current, config } : current))

      return { previous }
    },
    onError: (error, { generation }, context) => {
      if (generation === saveGeneration.current && context?.previous) {
        queryClient.setQueryData(queryKey, context.previous)
      }

      notifyError(error, o.saveFailed)
    },
    onSuccess: (payload, { generation }) => {
      if (generation === saveGeneration.current) {
        queryClient.setQueryData(queryKey, payload)
      }
    }
  })

  const commit = (config: OrchestratorConfig) => {
    saveGeneration.current += 1
    save.mutate({ config, generation: saveGeneration.current })
  }

  if (flow.isError) {
    return (
      <section {...props} className="grid h-full place-items-center bg-(--ui-chat-surface-background) px-6">
        <ErrorState description={String(flow.error)} title={o.loadFailed}>
          <Button onClick={() => void flow.refetch()} variant="secondary">
            {o.retry}
          </Button>
        </ErrorState>
      </section>
    )
  }

  if (!flow.data) {
    return <PageLoader />
  }

  const { assignments, config } = flow.data

  const providers = (modelOptions.data?.providers ?? []).filter(
    provider => provider.authenticated !== false && (provider.models ?? []).length > 0
  )

  const canRun = Boolean(run) && config.enabled && task.trim().length > 0

  return (
    <section
      {...props}
      className="flex h-full min-w-0 flex-col overflow-hidden bg-(--ui-chat-surface-background)"
      data-testid="orchestrator-view"
    >
      <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
        <div className="mx-auto grid w-full max-w-2xl gap-8 px-6 pb-12 pt-[calc(var(--titlebar-height,34px)+1.5rem)]">
          <header className="grid gap-1.5">
            <h1 className="text-xl font-semibold tracking-tight text-(--ui-text-primary)">{o.title}</h1>
            <p className="text-sm leading-5 text-(--ui-text-secondary)">{o.subtitle}</p>
          </header>

          <div className="flex items-start justify-between gap-6">
            <label className="grid gap-1" htmlFor="orchestrator-enabled">
              <span className="text-sm font-medium text-(--ui-text-primary)">{o.enable}</span>
              <FieldHint>{o.enableHint}</FieldHint>
            </label>
            <Switch
              checked={config.enabled}
              id="orchestrator-enabled"
              onCheckedChange={enabled => commit({ ...config, enabled })}
            />
          </div>

          <section className="grid gap-2">
            <h2 className="text-sm font-semibold text-(--ui-text-primary)">{o.rolesTitle}</h2>
            <FieldHint>{o.rolesHint}</FieldHint>
            <ul className="mt-1 divide-y divide-(--ui-stroke-tertiary)">
              {ORCHESTRATOR_ROLE_IDS.map(role => (
                <RoleRow
                  assignment={assignments[role]}
                  choice={roleChoice(config.roles[role])}
                  key={role}
                  onChoose={choice => commit(withRoleChoice(config, role, choice))}
                  providers={providers}
                  role={role}
                />
              ))}
            </ul>
          </section>

          <section className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_14rem] sm:items-start sm:gap-6">
            <label className="grid gap-1" htmlFor="orchestrator-rounds">
              <span className="text-sm font-medium text-(--ui-text-primary)">{o.rounds}</span>
              <FieldHint>{o.roundsHint}</FieldHint>
            </label>
            <Select
              onValueChange={value => commit(withReviewRounds(config, Number(value)))}
              value={String(config.max_review_rounds)}
            >
              <SelectTrigger className="h-9 rounded-md" id="orchestrator-rounds">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ROUND_OPTIONS.map(n => (
                  <SelectItem key={n} value={String(n)}>
                    {o.roundsValue(n)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </section>

          <section className="grid gap-2">
            <h2 className="text-sm font-semibold text-(--ui-text-primary)">{o.runTitle}</h2>
            <Textarea
              aria-label={o.runTitle}
              className="min-h-28 resize-y"
              onChange={event => setTask(event.target.value)}
              placeholder={o.taskPlaceholder}
              value={task}
            />
            <div className="flex items-center justify-between gap-4">
              <FieldHint>{config.enabled ? '' : o.runNeedsEnable}</FieldHint>
              <Button
                disabled={!canRun}
                onClick={() => {
                  run?.(orchestratePrompt(task))
                  setTask('')
                }}
              >
                {o.run}
              </Button>
            </div>
          </section>
        </div>
      </div>
    </section>
  )
}

interface RoleRowProps {
  assignment: OrchestratorAssignment | undefined
  choice: string
  onChoose: (choice: string) => void
  providers: ModelOptionProvider[]
  role: OrchestratorRoleId
}

function RoleRow({ assignment, choice, onChoose, providers, role }: RoleRowProps) {
  const { t } = useI18n()
  const o = t.orchestrator
  const copy = o.roles[role]
  const selectId = `orchestrator-role-${role}`

  // A pinned model that has left the catalog would render Radix's blank
  // trigger; keep it visible and re-selectable instead of silently dropping it.
  const choiceKnown =
    choice === AUTO_CHOICE ||
    providers.some(provider => (provider.models ?? []).some(model => `${provider.slug}:${model}` === choice))

  const resolved =
    choice !== AUTO_CHOICE ? o.pinned : assignment?.model ? o.autoPick(assignment.model) : o.autoSessionModel

  return (
    <li className="grid gap-2 py-3 sm:grid-cols-[minmax(0,1fr)_14rem] sm:items-start sm:gap-6">
      <div className="grid gap-0.5">
        <label className="text-sm font-medium text-(--ui-text-primary)" htmlFor={selectId}>
          {copy.title}
        </label>
        <p className="text-xs leading-4 text-(--ui-text-secondary)">{copy.description}</p>
      </div>
      <div className="grid min-w-0 gap-1">
        <Select onValueChange={onChoose} value={choice}>
          <SelectTrigger aria-label={o.pickModel(copy.title)} className="h-9 rounded-md" id={selectId}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={AUTO_CHOICE}>{o.auto}</SelectItem>
            {!choiceKnown && (
              <SelectItem className="font-mono" value={choice}>
                {choice.slice(choice.indexOf(':') + 1)}
              </SelectItem>
            )}
            {providers.map(provider => (
              <SelectGroup key={provider.slug}>
                <SelectLabel>{provider.name}</SelectLabel>
                {(provider.models ?? []).map(model => (
                  <SelectItem
                    className="font-mono"
                    key={`${provider.slug}:${model}`}
                    value={`${provider.slug}:${model}`}
                  >
                    {model}
                  </SelectItem>
                ))}
              </SelectGroup>
            ))}
          </SelectContent>
        </Select>
        <p
          className="truncate text-[0.66rem] leading-4 text-(--ui-text-tertiary)"
          title={choice === AUTO_CHOICE ? assignment?.reason : undefined}
        >
          {resolved}
        </p>
      </div>
    </li>
  )
}
