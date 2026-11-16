import { atom } from 'nanostores'

export interface SessionModelRecord {
  id: string
  sessionId: string
  filename: string
  name: string
  url: string
  localPath: string
  format: 'glb' | 'png' | 'gltf' | 'obj'
  prompt: string
  sizeBytes?: number
  durationSeconds?: number
  timestamp: number
  vertices?: number
  triangles?: number
}

/**
 * Stores 3D models generated per session context.
 * Keyed by sessionId (or '__draft__' when in a new chat).
 */
export const $session3DModels = atom<Record<string, SessionModelRecord[]>>({})

/** Active model selected in the session models tray for preview */
export const $activePreviewModel = atom<SessionModelRecord | null>(null)

/** Whether the session 3D models drawer is open */
export const $sessionModelsTrayOpen = atom<boolean>(false)

export function recordSessionModel(sessionId: string, model: Omit<SessionModelRecord, 'id' | 'timestamp'>): SessionModelRecord {
  const current = $session3DModels.get()
  const key = sessionId || '__draft__'
  const existingList = current[key] || []

  // Avoid duplicate records by filename or localPath
  const isDuplicate = existingList.some(
    m => m.filename === model.filename || (model.localPath && m.localPath === model.localPath)
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

export function getSessionModels(sessionId: string | null): SessionModelRecord[] {
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
