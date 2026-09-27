import { atom, computed } from 'nanostores'

import { MOUSE_TRACKING } from '../config/env.js'
import { ZERO } from '../domain/usage.js'
import { bootTheme } from '../lib/themeBoot.js'
import { DEFAULT_THEME } from '../theme.js'

import { DEFAULT_INDICATOR_STYLE, type UiState } from './interfaces.js'

const buildUiState = (): UiState => ({
  battery: false,
  batteryStatus: null,
  bgTasks: new Set(),
  busy: false,
  busyInputMode: 'queue',
  compact: false,
  detailsMode: 'collapsed',
  detailsModeCommandOverride: false,
  focusView: false,
  indicatorStyle: DEFAULT_INDICATOR_STYLE,
  info: null,
  liveSessionCount: 0,
  liveSessions: [],
  inlineDiffs: true,
  mouseTracking: MOUSE_TRACKING,
  notice: null,
  pasteCollapseLines: 5,
  pasteCollapseChars: 2000,
  sections: {},
  sessionTitle: '',
  showReasoning: false,
  sid: null,
  status: 'starting Jetts-TUI…',
  statusBar: 'top',
  streaming: true,
  // Last session's resolved theme paints frame one (flash-free boot, like
  // the desktop's freeide-boot-* keys); DEFAULT_THEME only on first launch.
  theme: bootTheme ?? DEFAULT_THEME,
  usage: ZERO
})

export const $uiState = atom<UiState>(buildUiState())

export const $uiTheme = computed($uiState, state => state.theme)
export const $uiSessionId = computed($uiState, state => state.sid)

// Unread delta per live session id, fed by the 1.5s active_list poll. Kept as
// a separate atom (not part of UiState) so a background session finishing a
// turn re-renders only the resident sidebar/pane, not the whole TUI. A value
// of -1 means "changed" (message count reset by resume/compaction) — renderers
// show a dot instead of a number.
export const $unreadBySession = atom<Map<string, number>>(new Map())

export const patchUnreadBySession = (next: Map<string, number>) => $unreadBySession.set(next)

export const getUiState = () => $uiState.get()

export const patchUiState = (next: Partial<UiState> | ((state: UiState) => UiState)) =>
  $uiState.set(typeof next === 'function' ? next($uiState.get()) : { ...$uiState.get(), ...next })

export const resetUiState = () => $uiState.set(buildUiState())
