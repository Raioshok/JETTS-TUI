export type WorkMode = 'accept-edits' | 'default' | 'plan'

export const isWorkMode = (value: string): value is WorkMode =>
  value === 'default' || value === 'accept-edits' || value === 'plan'

export const workModeNotice = (mode: string, deferred = false): string => {
  const label =
    mode === 'accept-edits' ? 'accept edits' : mode === 'plan' ? 'plan (read-only)' : 'default'

  return `mode → ${label}${deferred ? ' (applies next turn)' : ''}`
}
