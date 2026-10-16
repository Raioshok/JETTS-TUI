import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useI18n } from '@/i18n'
import {
  type DiscordActivity,
  type DiscordPresenceSettings,
  type DiscordPresenceStatus,
  getDiscordApplication,
  getDiscordPresence,
  setDiscordApplication,
  setDiscordPresenceEnabled,
  updateDiscordPresenceSettings
} from '@/jettstui'
import { errorText } from '@/lib/error-text'
import { DiscordIcon, ExternalLink, Eye, Loader2, Lock, Palette } from '@/lib/icons'
import { cn } from '@/lib/utils'
import { notifyError } from '@/store/notifications'

import { useOnProfileSwitch } from '../hooks/use-on-profile-switch'

import { EmptyState, ListRow, Pill, SettingsSection, ToggleRow } from './primitives'

const STATUS_KEY = ['discord-presence', 'status'] as const
const PORTAL_URL = 'https://discord.com/developers/applications'

type EditableSettings = Parameters<typeof updateDiscordPresenceSettings>[0]

const PRIVACY_KEYS = [
  ['show_model', 'showModel', 'showModelDesc'],
  ['show_project', 'showProject', 'showProjectDesc'],
  ['show_tool_activity', 'showActivity', 'showActivityDesc'],
  ['show_elapsed', 'showElapsed', 'showElapsedDesc']
] as const

function isMissingBackend(error: unknown): boolean {
  return /\b404\b|not found/i.test(error instanceof Error ? error.message : String(error ?? ''))
}

function formatElapsed(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  const h = Math.floor(s / 3600)
  const mm = String(Math.floor((s % 3600) / 60)).padStart(2, '0')
  const ss = String(s % 60).padStart(2, '0')

  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}

/** Seconds since `start` (unix seconds), ticking once a second. */
function useElapsed(start?: number): null | number {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (!start) {
      return
    }

    const id = window.setInterval(() => setNow(Date.now()), 1000)

    return () => window.clearInterval(id)
  }, [start])

  return start ? now / 1000 - start : null
}

/** Text field that saves on blur/Enter, so typing doesn't write config per keystroke. */
function CommitInput({
  onCommit,
  value,
  ...props
}: Omit<React.ComponentProps<typeof Input>, 'onChange' | 'value'> & {
  onCommit: (value: string) => void
  value: string
}) {
  const [draft, setDraft] = useState(value)

  useEffect(() => setDraft(value), [value])

  const commit = () => {
    if (draft.trim() !== value) {
      onCommit(draft.trim())
    }
  }

  return (
    <Input
      {...props}
      onBlur={commit}
      onChange={e => setDraft(e.target.value)}
      onKeyDown={e => {
        if (e.key === 'Enter') {
          commit()
        }
      }}
      value={draft}
    />
  )
}

function PresenceCard({
  activity,
  appName,
  iconUrl
}: {
  activity: DiscordActivity | null
  appName: string
  iconUrl: string
}) {
  const { t } = useI18n()
  const c = t.settings.discordPresence
  const elapsed = useElapsed(activity?.timestamps?.start)
  const image = activity?.assets?.large_image?.startsWith('https://') ? activity.assets.large_image : iconUrl

  return (
    <div className="rounded-xl border border-border/70 bg-(--ui-bg-secondary) p-4">
      <div className="mb-3 text-[0.68rem] font-semibold tracking-wide text-muted-foreground uppercase">{c.playing}</div>
      <div className="flex gap-3">
        <div className="flex size-16 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-(--ui-bg-tertiary)">
          {image ? (
            <img alt="" className="size-full object-cover" src={image} />
          ) : (
            <DiscordIcon className="size-7 text-muted-foreground" />
          )}
        </div>
        <div className="min-w-0 text-[length:var(--conversation-caption-font-size)] leading-snug">
          <div className="truncate font-semibold text-foreground">{appName}</div>
          {activity?.details && <div className="truncate text-foreground/90">{activity.details}</div>}
          {activity?.state && <div className="truncate text-muted-foreground">{activity.state}</div>}
          {elapsed !== null && (
            <div className="truncate font-mono text-[0.7rem] text-muted-foreground">
              {c.elapsed(formatElapsed(elapsed))}
            </div>
          )}
        </div>
      </div>
      {activity?.buttons && activity.buttons.length > 0 && (
        <div className="mt-3 grid gap-1.5">
          {activity.buttons.map(button => (
            <div
              className="truncate rounded-md bg-(--ui-bg-tertiary) px-3 py-1.5 text-center text-[0.72rem] font-medium text-foreground"
              key={button.url}
              title={button.url}
            >
              {button.label}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function DiscordRpcSettings() {
  const { t } = useI18n()
  const c = t.settings.discordPresence
  const queryClient = useQueryClient()
  const [appDraft, setAppDraft] = useState<null | string>(null)
  const [verifying, setVerifying] = useState(false)
  const [appError, setAppError] = useState('')

  const statusQuery = useQuery({
    queryKey: STATUS_KEY,
    queryFn: getDiscordPresence,
    refetchInterval: 5000,
    retry: (count, error) => !isMissingBackend(error) && count < 2
  })

  useOnProfileSwitch(() => {
    setAppDraft(null)
    setAppError('')
    void queryClient.invalidateQueries({ queryKey: ['discord-presence'] })
  })

  const status = statusQuery.data
  const settings = status?.settings
  const clientId = settings?.client_id ?? ''

  const appQuery = useQuery({
    queryKey: ['discord-presence', 'application', clientId],
    queryFn: getDiscordApplication,
    enabled: Boolean(clientId),
    staleTime: Infinity,
    retry: false
  })

  if (statusQuery.error && isMissingBackend(statusQuery.error)) {
    return <EmptyState description={c.unavailable} title={t.settings.sections.discord ?? 'Discord Presence'} />
  }

  if (!status || !settings) {
    return (
      <div className="flex items-center gap-2 py-6 text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
      </div>
    )
  }

  const publish = (next: DiscordPresenceStatus) => queryClient.setQueryData(STATUS_KEY, next)

  async function run(action: () => Promise<DiscordPresenceStatus>) {
    try {
      publish(await action())
    } catch (error) {
      notifyError(error, c.saveFailed)
      void statusQuery.refetch()
    }
  }

  // Optimistic: paint the change now, let the server's answer have the last word.
  function change(changes: EditableSettings) {
    if (status && settings) {
      publish({ ...status, settings: { ...settings, ...changes } as DiscordPresenceSettings })
    }

    void run(() => updateDiscordPresenceSettings(changes))
  }

  async function verifyApplication() {
    const value = (appDraft ?? clientId).trim()

    if (!value) {
      return
    }

    setVerifying(true)
    setAppError('')

    try {
      const result = await setDiscordApplication(value)
      queryClient.setQueryData(['discord-presence', 'application', result.application.id], result.application)
      publish(result.status)
      setAppDraft(null)
    } catch (error) {
      setAppError(errorText(error, c.appInvalid) || c.appInvalid)
    } finally {
      setVerifying(false)
    }
  }

  const userName = status.user.display_name || status.user.username || ''

  const statusPill = !status.enabled ? (
    <Pill>{c.statusOff}</Pill>
  ) : !status.configured ? (
    <Pill tone="warn">{c.statusNeedsApp}</Pill>
  ) : status.connected ? (
    <Pill tone="primary">{c.statusConnected(userName || 'Discord')}</Pill>
  ) : (
    <Pill tone="warn">{c.statusWaiting}</Pill>
  )

  const application = appQuery.data
  const appName = application?.name || 'JettsTUI'
  const draftValue = appDraft ?? clientId

  return (
    <div className="mb-6">
      <SettingsSection aside={statusPill} icon={DiscordIcon} title={t.settings.sections.discord ?? 'Discord Presence'}>
        <p className="mb-1 text-[length:var(--conversation-caption-font-size)] text-(--ui-text-tertiary)">{c.intro}</p>
        <ToggleRow
          checked={status.enabled}
          description={
            status.enabled && status.configured && !status.connected && status.error ? status.error : c.enableDesc
          }
          label={c.enableTitle}
          onChange={on => void run(() => setDiscordPresenceEnabled(on))}
        />
        <ListRow
          action={
            <div className="flex gap-2">
              <Input
                aria-label={c.appPlaceholder}
                className="font-mono"
                inputMode="numeric"
                onChange={e => {
                  setAppDraft(e.target.value)
                  setAppError('')
                }}
                onKeyDown={e => {
                  if (e.key === 'Enter') {
                    void verifyApplication()
                  }
                }}
                placeholder={c.appPlaceholder}
                value={draftValue}
              />
              <Button
                disabled={verifying || !draftValue.trim() || (appDraft === null && Boolean(application))}
                onClick={() => void verifyApplication()}
                size="sm"
                variant="outline"
              >
                {verifying ? <Loader2 className="size-3.5 animate-spin" /> : c.verify}
              </Button>
            </div>
          }
          below={
            <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[length:var(--conversation-caption-font-size)]">
              {appError ? (
                <span className="text-destructive">{appError}</span>
              ) : (
                application && (
                  <span className="text-foreground/80">{c.appSaved(application.name || application.id)}</span>
                )
              )}
              <a
                className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
                href={PORTAL_URL}
                rel="noreferrer"
                target="_blank"
              >
                {c.openPortal}
                <ExternalLink className="size-3" />
              </a>
            </div>
          }
          description={c.appDesc}
          title={c.appTitle}
        />
      </SettingsSection>

      <SettingsSection icon={Eye} title={c.previewTitle}>
        <p className="mb-2 text-[length:var(--conversation-caption-font-size)] text-(--ui-text-tertiary)">
          {c.previewDesc}
        </p>
        <PresenceCard
          activity={status.connected && status.activity ? status.activity : status.preview}
          appName={appName}
          iconUrl={application?.icon_url ?? ''}
        />
      </SettingsSection>

      <SettingsSection icon={Palette} title={c.styleTitle}>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {status.presets.map(preset => {
            const active = settings.preset === preset.id

            return (
              <button
                aria-pressed={active}
                className={cn(
                  'rounded-lg border px-3 py-2 text-left text-[length:var(--conversation-caption-font-size)] transition',
                  active
                    ? 'border-primary bg-primary/10 font-medium text-foreground'
                    : 'border-border/70 text-muted-foreground hover:bg-(--chrome-action-hover) hover:text-foreground'
                )}
                key={preset.id}
                onClick={() => change({ preset: preset.id })}
                type="button"
              >
                {c.presets[preset.id] ?? preset.label}
              </button>
            )
          })}
        </div>
      </SettingsSection>

      <SettingsSection icon={Lock} title={c.privacyTitle}>
        {PRIVACY_KEYS.map(([key, label, description]) => (
          <ToggleRow
            checked={settings[key]}
            description={c[description]}
            key={key}
            label={c[label]}
            onChange={on => change({ [key]: on })}
          />
        ))}
        <ListRow
          action={
            <CommitInput
              aria-label={c.idleTitle}
              className="w-24"
              inputMode="numeric"
              min={0}
              onCommit={value => {
                const minutes = Number.parseInt(value, 10)

                if (Number.isFinite(minutes) && minutes >= 0) {
                  change({ idle_timeout_minutes: minutes })
                }
              }}
              type="number"
              value={String(settings.idle_timeout_minutes)}
            />
          }
          description={c.idleDesc}
          title={c.idleTitle}
        />
      </SettingsSection>

      <SettingsSection icon={Palette} title={c.customTitle}>
        <p className="mb-1 text-[length:var(--conversation-caption-font-size)] text-(--ui-text-tertiary)">
          {c.customDesc}
        </p>
        <ListRow
          action={
            <CommitInput
              aria-label={c.detailsLabel}
              maxLength={128}
              onCommit={value => change({ details: value })}
              placeholder={status.preview?.details}
              value={settings.details}
            />
          }
          title={c.detailsLabel}
        />
        <ListRow
          action={
            <CommitInput
              aria-label={c.stateLabel}
              maxLength={128}
              onCommit={value => change({ state: value })}
              placeholder={status.preview?.state}
              value={settings.state}
            />
          }
          title={c.stateLabel}
        />
      </SettingsSection>
    </div>
  )
}
