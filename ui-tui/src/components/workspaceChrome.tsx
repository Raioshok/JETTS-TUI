import { Box, stringWidth, Text } from '@jetts-tui/ink'

import type { Theme } from '../theme.js'

type WorkMode = 'accept-edits' | 'default' | 'plan' | undefined

const shortModel = (model: string) => {
  const leaf = model.split('/').pop() || model

  return leaf.replace(/[-_]/g, ' ')
}

const shortPath = (value: string) => {
  const normalized = value.replace(/\\/g, '/')
  const parts = normalized.split('/').filter(Boolean)

  if (parts.length <= 2) {
    return value || 'workspace'
  }

  return `…/${parts.slice(-2).join('/')}`
}

const modeLabel = (mode: WorkMode) => (mode === 'plan' ? 'PLAN' : mode === 'accept-edits' ? 'ACCEPT EDITS' : 'DEFAULT')

const modeColor = (mode: WorkMode, t: Theme) =>
  mode === 'plan' ? t.color.warn : mode === 'accept-edits' ? t.color.accent : t.color.muted

export interface WorkspaceHeaderProps {
  brand: string
  busy: boolean
  cols: number
  cwd: string
  mode?: WorkMode
  model: string
  project?: string
  t: Theme
}

/** Persistent, responsive context chrome for the active workspace. */
export function WorkspaceHeader({ brand, busy, cols, cwd, mode, model, project, t }: WorkspaceHeaderProps) {
  const width = Math.max(1, cols - 2)
  const title = project || shortPath(cwd)
  const showModel = width >= 58 && Boolean(model)
  const showMode = width >= 42

  return (
    <Box flexDirection="column" flexShrink={0} paddingX={1}>
      <Box height={1} justifyContent="space-between" width={width}>
        <Box flexShrink={1} overflow="hidden">
          <Text bold color={t.color.primary} wrap="truncate-end">
            {busy ? '◆' : '◇'} {brand}
          </Text>
          <Text color={t.color.muted} wrap="truncate-end">
            {'  /  '}
            {title}
          </Text>
        </Box>

        {(showModel || showMode) && (
          <Box flexShrink={0}>
            {showModel && <Text color={t.color.label}>{shortModel(model)}</Text>}
            {showModel && showMode && <Text color={t.color.border}>{'  ·  '}</Text>}
            {showMode && (
              <Text bold={mode !== 'default' && mode !== undefined} color={modeColor(mode, t)}>
                {modeLabel(mode)}
              </Text>
            )}
          </Box>
        )}
      </Box>
      <Text color={t.color.border}>{'─'.repeat(width)}</Text>
    </Box>
  )
}

export interface ComposerToolbarProps {
  busy: boolean
  cols: number
  mode?: WorkMode
  queueCount: number
  t: Theme
}

/** A quiet command strip that separates conversation from composition. */
export function ComposerToolbar({ busy, cols, mode, queueCount, t }: ComposerToolbarProps) {
  const width = Math.max(1, cols - 2)
  const wide = width >= 76
  const medium = width >= 48

  const left =
    width < 22
      ? busy
        ? 'STEER'
        : queueCount > 0
          ? `${queueCount} QUEUED`
          : 'MESSAGE'
      : busy
        ? 'STEER AGENT'
        : queueCount > 0
          ? `MESSAGE · ${queueCount} QUEUED`
          : 'NEW MESSAGE'

  const hint = wide
    ? 'Enter send  ·  Shift+Enter newline  ·  Shift+Tab mode'
    : medium
      ? 'Enter send  ·  Shift+Tab mode'
      : width >= 32
        ? modeLabel(mode)
        : ''

  const used = stringWidth(left) + stringWidth(hint) + (hint ? 5 : 3)
  const rule = '─'.repeat(Math.max(0, width - used))

  return (
    <Box height={1} justifyContent="space-between" width={width}>
      <Box flexShrink={1} overflow="hidden">
        <Text bold color={busy ? t.color.warn : t.color.accent} wrap="truncate-end">
          {busy ? '●' : '◆'} {left}
        </Text>
      </Box>
      {rule ? <Text color={t.color.border}>{rule}</Text> : null}
      {hint ? <Text color={t.color.muted}>{hint}</Text> : null}
    </Box>
  )
}

export function TurnDivider({ t }: { t: Theme }) {
  return (
    <Box marginTop={1}>
      <Text color={t.color.border}>── </Text>
      <Text color={t.color.muted} dimColor>
        next turn
      </Text>
      <Text color={t.color.border}> ──</Text>
    </Box>
  )
}
