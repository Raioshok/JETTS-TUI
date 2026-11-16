import { recordSessionModel } from '@/store/blender-models'
import { $activeSessionId } from '@/store/session'

export interface BlenderModelResultData {
  success: boolean
  prompt?: string
  format?: 'glb' | 'png' | 'gltf' | 'obj'
  output_path?: string
  filename?: string
  file_size_bytes?: number
  duration_seconds?: number
  message?: string
  displayUrl: string
}

function recordFromUnknown(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>
  }

  if (typeof value !== 'string' || !value.trim()) {
    return null
  }

  try {
    const parsed = JSON.parse(value)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : null
  } catch {
    return null
  }
}

/**
 * Resolve display URL for a model or render from path or filename.
 */
export function resolveModelDisplayUrl(pathOrFilename: string): string {
  if (!pathOrFilename) return ''

  if (/^(?:https?|data|blob):/i.test(pathOrFilename)) {
    return pathOrFilename
  }

  // Extract filename
  const filename = pathOrFilename.split(/[\\/]/).pop() || pathOrFilename

  // Check if it's served by the blender plugin api
  return `/api/plugins/blender/files/${encodeURIComponent(filename)}`
}

/**
 * Extract structured model data from a blender tool result.
 */
export function blenderModelFromResult(result: unknown): BlenderModelResultData | null {
  const record = recordFromUnknown(result)
  if (!record || record.success === false) {
    return null
  }

  const outputPath = typeof record.output_path === 'string' ? record.output_path : ''
  const filename = typeof record.filename === 'string'
    ? record.filename
    : outputPath.split(/[\\/]/).pop() || 'model.glb'

  const formatRaw = typeof record.format === 'string'
    ? record.format.toLowerCase()
    : filename.split('.').pop()?.toLowerCase() || 'glb'
  const format: 'glb' | 'png' | 'gltf' | 'obj' =
    formatRaw === 'png' ? 'png' : formatRaw === 'obj' ? 'obj' : formatRaw === 'gltf' ? 'gltf' : 'glb'

  const prompt = typeof record.prompt === 'string' ? record.prompt : ''
  const fileSizeBytes = typeof record.file_size_bytes === 'number' ? record.file_size_bytes : undefined
  const durationSeconds = typeof record.duration_seconds === 'number' ? record.duration_seconds : undefined

  const displayUrl = resolveModelDisplayUrl(outputPath || filename)

  // Automatically record this model into the session's 3D history context!
  const sessionId = $activeSessionId.get() || '__draft__'
  recordSessionModel(sessionId, {
    sessionId,
    filename,
    name: prompt ? prompt.slice(0, 35) : filename,
    url: displayUrl,
    localPath: outputPath,
    format,
    prompt,
    sizeBytes: fileSizeBytes,
    durationSeconds
  })

  return {
    success: true,
    prompt,
    format,
    output_path: outputPath,
    filename,
    file_size_bytes: fileSizeBytes,
    duration_seconds: durationSeconds,
    displayUrl
  }
}
