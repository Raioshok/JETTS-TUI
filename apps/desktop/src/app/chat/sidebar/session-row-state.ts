export type SessionDotState = 'background' | 'idle' | 'needs-input' | 'stalled' | 'unread' | 'working'

interface SessionRowState {
  hasBackground: boolean
  isStalled: boolean
  isUnread: boolean
  isWorking: boolean
  needsInput: boolean
}

/** Resolve the sidebar dot's mutually-exclusive display state by priority. */
export function sessionDotState({
  hasBackground,
  isStalled,
  isUnread,
  isWorking,
  needsInput
}: SessionRowState): SessionDotState {
  if (needsInput) {
    return 'needs-input'
  }

  if (isWorking) {
    return isStalled ? 'stalled' : 'working'
  }

  if (hasBackground) {
    return 'background'
  }

  return isUnread ? 'unread' : 'idle'
}

/** A quiet turn is still authoritatively running. Keep the unmistakable row
 * arc until the gateway reports completion; only a blocking prompt suppresses
 * it in favour of the needs-input treatment. */
export function sessionShowsRunningArc({
  isWorking,
  needsInput
}: Pick<SessionRowState, 'isWorking' | 'needsInput'>): boolean {
  return isWorking && !needsInput
}

const comparable = (text: string) =>
  text
    .replace(/[…\s]+$/u, '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()

/**
 * The secondary line under a session title, or null when it would only repeat
 * the title. Untitled sessions fall back to their first message for the title,
 * so title and preview are often the same text — showing both is noise.
 */
export function sessionPreviewLine(preview: null | string | undefined, title: string): null | string {
  const line = preview?.replace(/\s+/g, ' ').trim()

  if (!line) {
    return null
  }

  const a = comparable(line)
  const b = comparable(title)

  return !b || a.startsWith(b) || b.startsWith(a) ? null : line
}
