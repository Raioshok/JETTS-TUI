import { Box, Text } from '@jetts-tui/ink'

import type { SessionActiveItem } from '../gatewayTypes.js'
import { commsSessions, relativeTime } from '../lib/residentActivity.js'
import type { Theme } from '../theme.js'
import type { SubagentProgress } from '../types.js'

export const RESIDENT_WORKSPACE_MIN_COLS = 118
export const RESIDENT_WORKSPACE_MIN_ROWS = 30
export const RESIDENT_SIDEBAR_COLS = 29

export type ResidentWorkspacePref = 'auto' | 'off' | 'on'

export const shouldUseResidentWorkspace = (
  cols: number,
  rows: number,
  sessionCount: number,
  pref: ResidentWorkspacePref = 'auto'
) => {
  if (pref === 'off') {return false}
  const sized = cols >= RESIDENT_WORKSPACE_MIN_COLS && rows >= RESIDENT_WORKSPACE_MIN_ROWS && sessionCount > 0

  return pref === 'on' ? sessionCount > 0 : sized
}

export const residentSessionLabel = (session: SessionActiveItem, index: number) =>
  session.title?.trim() || `agent${index + 1}`

export const residentCurrentSessionIndex = (sessions: readonly SessionActiveItem[], currentSessionId: null | string) => {
  const explicit = currentSessionId ? sessions.findIndex(session => session.id === currentSessionId) : -1

  return explicit >= 0 ? explicit : Math.max(0, sessions.findIndex(session => session.current))
}

const statusGlyph = (status: SessionActiveItem['status']) => {
  if (status === 'working') {return '●'}

  if (status === 'waiting') {return '!'}

  if (status === 'starting') {return '…'}

  return '○'
}

const shortModel = (model = '') => model.split('/').pop() || 'default'

export const activeResidentAgents = (subagents: readonly SubagentProgress[]) =>
  subagents.filter(agent => agent.status === 'running' || agent.status === 'queued')

export const visibleResidentAgents = (subagents: readonly SubagentProgress[]) => [
  ...activeResidentAgents(subagents),
  ...subagents.filter(agent => agent.status !== 'running' && agent.status !== 'queued')
]

const agentActivity = (agent: SubagentProgress) =>
  agent.notes.at(-1) || agent.thinking.at(-1) || agent.tools.at(-1) || agent.summary || agent.goal

interface ResidentWorkspaceSidebarProps {
  currentSessionId: null | string
  onNew: () => void
  onOpenAgents: () => void
  onSelect: (id: string) => void
  sessions: SessionActiveItem[]
  subagents: SubagentProgress[]
  t: Theme
  unread: Map<string, number>
}

/** Persistent session navigation and cross-session activity for wide terminals. */
export function ResidentWorkspaceSidebar({
  currentSessionId,
  onNew,
  onOpenAgents,
  onSelect,
  sessions,
  subagents,
  t,
  unread
}: ResidentWorkspaceSidebarProps) {
  const runningAgents = activeResidentAgents(subagents)
  const visibleAgents = visibleResidentAgents(subagents)

  return (
    <Box flexDirection="column" flexShrink={0} height="100%" marginRight={1} width={RESIDENT_SIDEBAR_COLS}>
      <Box borderColor={t.color.border} borderStyle="round" flexDirection="column" flexGrow={1} paddingX={1}>
        <Box justifyContent="space-between">
          <Text bold color={t.color.label}>Sessions</Text>
          <Text color={t.color.muted}>{sessions.length} live</Text>
        </Box>

        <Text color={t.color.border}>{'─'.repeat(RESIDENT_SIDEBAR_COLS - 4)}</Text>

        {sessions.slice(0, 9).map((session, index) => {
          const current = residentCurrentSessionIndex(sessions, currentSessionId) === index

          return (
            <Box
              backgroundColor={current ? t.color.completionCurrentBg : undefined}
              height={1}
              key={session.id}
              onClick={() => onSelect(session.id)}
            >
              <Box flexShrink={0}>
                <Text color={current ? t.color.accent : session.status === 'working' ? t.color.ok : t.color.muted}>
                  {statusGlyph(session.status)}{' '}
                </Text>
                <Text color={t.color.muted}>{index + 1} </Text>
              </Box>
              {/* One line per session: long titles truncate instead of wrapping. */}
              <Box flexGrow={1} flexShrink={1} overflow="hidden">
                <Text bold={current} color={current ? t.color.text : t.color.label} wrap="truncate-end">
                  {residentSessionLabel(session, index)}
                </Text>
              </Box>
              {(() => {
                const n = unread.get(session.id) ?? 0

                return n > 0 ? <Text bold color={t.color.warn}> +{n}</Text> : n < 0 ? <Text color={t.color.warn}> •</Text> : null
              })()}
              {current ? <Text color={t.color.accent}> ◀</Text> : null}
            </Box>
          )
        })}

        <Box marginTop={1} onClick={onNew}>
          <Text color={t.color.accent}>＋ new session</Text>
        </Box>

        {subagents.length > 0 ? (
          <Box flexDirection="column" marginTop={1}>
            <Box onClick={onOpenAgents}>
              <Text bold color={t.color.label}>Child agents</Text>
              <Text color={t.color.muted}> {runningAgents.length} active ›</Text>
            </Box>
            {visibleAgents.slice(0, 4).map(agent => (
              <Box key={agent.id} onClick={onOpenAgents}>
                <Text color={agent.status === 'running' ? t.color.ok : t.color.muted}>
                  {agent.status === 'running' ? '●' : agent.status === 'queued' ? '○' : '✓'}{' '}
                </Text>
                <Text color={t.color.text} wrap="truncate-end">{agent.goal}</Text>
              </Box>
            ))}
            {subagents.length > 4 ? <Text color={t.color.muted}>+{subagents.length - 4} more · /agents</Text> : null}
          </Box>
        ) : null}

        <Box flexGrow={1} />
        <Text color={t.color.muted}>Alt+1…9 target</Text>
        <Text color={t.color.muted}>Ctrl+X all sessions</Text>
      </Box>

      <Box borderColor={t.color.border} borderStyle="round" flexDirection="column" height={10} marginTop={1} paddingX={1}>
        <Box justifyContent="space-between">
          <Text bold color={t.color.label}>Comms</Text>
          <Text color={t.color.muted}>live</Text>
        </Box>
        {subagents.length > 0 ? visibleAgents.slice(0, 3).map(agent => (
          <Box flexDirection="column" key={agent.id} onClick={onOpenAgents}>
            <Text color={agent.status === 'running' ? t.color.ok : t.color.muted} wrap="truncate-end">
              {agent.status === 'running' ? '●' : '○'} {agent.goal}
            </Text>
            <Text color={t.color.muted} dimColor wrap="truncate-end">{'  '}{agentActivity(agent)}</Text>
          </Box>
        )) : commsSessions(sessions, 3).map(session => {
          const index = sessions.findIndex(s => s.id === session.id)
          const ts = relativeTime(session.last_active, Date.now())

          return (
            <Box flexDirection="column" key={session.id}>
              <Text color={session.status === 'working' ? t.color.ok : t.color.muted} wrap="truncate-end">
                {statusGlyph(session.status)} {residentSessionLabel(session, index)} · {session.status}{ts ? ` · ${ts}` : ''}
              </Text>
              {session.preview ? (
                <Text color={t.color.muted} dimColor wrap="truncate-end">
                  {'  '}{session.preview}
                </Text>
              ) : null}
            </Box>
          )
        })}
      </Box>
    </Box>
  )
}

interface ResidentSessionPreviewProps {
  index: number
  onSelect: (id: string) => void
  session: SessionActiveItem
  t: Theme
}

/** A live, non-focused session pane. Selecting it promotes it to the full transcript. */
export function ResidentSessionPreview({ index, onSelect, session, t }: ResidentSessionPreviewProps) {
  const ts = relativeTime(session.last_active, Date.now())

  return (
    <Box
      borderColor={session.status === 'waiting' ? t.color.warn : t.color.sessionBorder}
      borderStyle="round"
      flexDirection="column"
      flexShrink={0}
      height={6}
      marginBottom={1}
      onClick={() => onSelect(session.id)}
      paddingX={1}
    >
      <Box justifyContent="space-between">
        <Text bold color={session.status === 'working' ? t.color.ok : t.color.accent}>
          {statusGlyph(session.status)} {residentSessionLabel(session, index)}
        </Text>
        <Text color={t.color.muted}>Alt+{index + 1} · {shortModel(session.model)}{ts ? ` · ${ts}` : ''}</Text>
      </Box>
      <Text color={t.color.muted} wrap="truncate-end">
        {session.status} · {session.message_count ?? 0} messages
        {session.status === 'waiting' ? <Text color={t.color.warn}> · ⚑ needs input</Text> : null}
      </Text>
      <Text color={t.color.text} wrap="truncate-end">
        {session.preview || 'Ready for a task'}
      </Text>
    </Box>
  )
}

export function ResidentInputTarget({
  currentSessionId,
  sessions,
  t
}: {
  currentSessionId: null | string
  sessions: SessionActiveItem[]
  t: Theme
}) {
  const index = residentCurrentSessionIndex(sessions, currentSessionId)
  const target = sessions[index]

  if (!target) {return null}

  return (
    <Box>
      <Text color={t.color.muted}>To </Text>
      <Text bold color={t.color.accent}>{residentSessionLabel(target, index)}</Text>
    </Box>
  )
}
