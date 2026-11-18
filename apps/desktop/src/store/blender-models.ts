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

/**
 * Stores 3D models generated per session context.
 * Keyed by sessionId (or '__draft__' when in a new chat).
 */
export const $session3DModels = atom<Record<string, SessionModelRecord[]>>({})

/** Active model selected in the session models tray for preview */
export const $activePreviewModel = atom<null | SessionModelRecord>(null)

/** Whether the session 3D models drawer is open */
export const $sessionModelsTrayOpen = atom<boolean>(false)

/** Whether the Smart 3D quick-generator modal is open above the composer */
export const $smart3DModalOpen = atom<boolean>(false)

export function recordSessionModel(
  sessionId: string,
  model: Omit<SessionModelRecord, 'id' | 'timestamp'>
): SessionModelRecord {
  const current = $session3DModels.get()
  const key = sessionId || '__draft__'
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
  const key = sessionId || '__draft__'

  return current[key] || []
}

export function clearSessionModels(sessionId: string): void {
  const current = $session3DModels.get()
  const key = sessionId || '__draft__'
  const next = { ...current }
  delete next[key]
  $session3DModels.set(next)
}
