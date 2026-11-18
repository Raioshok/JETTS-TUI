import { atom } from 'nanostores'

export interface SessionModelRecord {
  durationSeconds?: number
  filename: string
  format: 'glb' | 'gltf' | 'obj' | 'png'
  id: string
  localPath: string
  name: string
  prompt: string
  sessionId: string
  sizeBytes?: number
  timestamp: number
  triangles?: number
  url: string
  vertices?: number
}

const DRAFT_KEY = '__draft__'

/**
 * Stores 3D models generated per session context.
 * Keyed by sessionId (or '__draft__' when in a new chat).
 */
export const $session3DModels = atom<Record<string, SessionModelRecord[]>>({})

/** Active model selected in the session models tray for preview */
export const $activePreviewModel = atom<null | SessionModelRecord>(null)

/** Whether the session 3D models drawer is open (main scope mirror) */
export const $sessionModelsTrayOpen = atom<boolean>(false)

/** Whether the Smart 3D quick-generator modal is open (main scope mirror) */
export const $smart3DModalOpen = atom<boolean>(false)

/** Per-composer-scope tray open map (`'main'` | `'tile:<id>'`) */
export const $sessionModelsTrayScopes = atom<Record<string, boolean>>({})

/** Per-composer-scope Smart 3D modal open map (`'main'` | `'tile:<id>'`) */
export const $smart3DModalScopes = atom<Record<string, boolean>>({})

export function setSessionModelsTrayOpen(open: boolean, scope = 'main'): void {
  $sessionModelsTrayScopes.set({ ...$sessionModelsTrayScopes.get(), [scope]: open })

  if (scope === 'main') {
    $sessionModelsTrayOpen.set(open)
  }
}

export function toggleSessionModelsTray(scope = 'main'): void {
  const current = scope === 'main' ? $sessionModelsTrayOpen.get() : Boolean($sessionModelsTrayScopes.get()[scope])
  setSessionModelsTrayOpen(!current, scope)
}

export function setSmart3DModalOpen(open: boolean, scope = 'main'): void {
  $smart3DModalScopes.set({ ...$smart3DModalScopes.get(), [scope]: open })

  if (scope === 'main') {
    $smart3DModalOpen.set(open)
  }
}

export function toggleSmart3DModal(scope = 'main'): void {
  const current = scope === 'main' ? $smart3DModalOpen.get() : Boolean($smart3DModalScopes.get()[scope])
  setSmart3DModalOpen(!current, scope)
}

export function recordSessionModel(
  sessionId: string,
  model: Omit<SessionModelRecord, 'id' | 'timestamp'>
): SessionModelRecord {
  const current = $session3DModels.get()
  const key = sessionId || DRAFT_KEY
  const existingList = current[key] || []

  const isDuplicate = existingList.some(
    m => m.filename === model.filename || (Boolean(model.localPath) && m.localPath === model.localPath)
  )

  const record: SessionModelRecord = {
    ...model,
    id: `${key}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    timestamp: Date.now()
  }

  if (!isDuplicate) {
    $session3DModels.set({
      ...current,
      [key]: [record, ...existingList]
    })
  }

  return record
}

export function getSessionModels(sessionId: null | string): SessionModelRecord[] {
  const current = $session3DModels.get()
  const key = sessionId || DRAFT_KEY

  return current[key] || []
}

export function clearSessionModels(sessionId: string): void {
  const current = $session3DModels.get()
  const key = sessionId || DRAFT_KEY
  const next = { ...current }
  delete next[key]
  $session3DModels.set(next)
}

/** Migrate draft-keyed 3D models onto the newly created runtime session id. */
export function migrateDraftSessionModels(nextSessionId: string): void {
  if (!nextSessionId || nextSessionId === DRAFT_KEY) {
    return
  }

  const current = $session3DModels.get()
  const draftList = current[DRAFT_KEY]

  if (!draftList || draftList.length === 0) {
    return
  }

  const existing = current[nextSessionId] || []

  const merged = [
    ...draftList
      .filter(
        d => !existing.some(e => e.filename === d.filename || (Boolean(d.localPath) && e.localPath === d.localPath))
      )
      .map(d => ({ ...d, sessionId: nextSessionId })),
    ...existing
  ]

  const next = { ...current, [nextSessionId]: merged }
  delete next[DRAFT_KEY]
  $session3DModels.set(next)
}

export function clearAllSessionModels(): void {
  $session3DModels.set({})
  $activePreviewModel.set(null)
  $sessionModelsTrayOpen.set(false)
  $smart3DModalOpen.set(false)
  $sessionModelsTrayScopes.set({})
  $smart3DModalScopes.set({})
}
