import { isRemoteGateway, mediaStreamUrl } from '@/lib/media'

export type BlenderAssetFormat = 'glb' | 'gltf' | 'obj' | 'png'

export interface BlenderModelResultData {
  displayUrl: string
  duration_seconds?: number
  file_size_bytes?: number
  filename: string
  format: BlenderAssetFormat
  message?: string
  output_path: string
  prompt: string
  success: boolean
}

function recordFromUnknown(value: unknown): null | Record<string, unknown> {
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

function isLocalPath(value: string): boolean {
  return /^(?:file:|\/|~\/|[a-z]:[\\/]|\\\\)/i.test(value)
}

export function detectModelFormat(pathOrName?: null | string): BlenderAssetFormat {
  const clean = (pathOrName || '').split(/[?#]/, 1)[0] || ''

  const decoded = (() => {
    try {
      return decodeURIComponent(clean)
    } catch {
      return clean
    }
  })()

  const ext = decoded.split('.').pop()?.toLowerCase()

  if (ext === 'png') {
    return 'png'
  }

  if (ext === 'obj') {
    return 'obj'
  }

  if (ext === 'gltf') {
    return 'gltf'
  }

  return 'glb'
}

/**
 * Resolve display URL for a model or render from path or filename.
 * Uses Electron's `jettstui-media://stream/...` protocol for local desktop paths
 * and falls back to `/api/plugins/blender/files/...` for web/remote contexts.
 */
export function resolveModelDisplayUrl(pathOrFilename: string): string {
  if (!pathOrFilename) {
    return ''
  }

  if (/^(?:https?|data|blob|jettstui-media):/i.test(pathOrFilename)) {
    return pathOrFilename
  }

  if (typeof window !== 'undefined' && window.jettstuiDesktop && !isRemoteGateway() && isLocalPath(pathOrFilename)) {
    return mediaStreamUrl(pathOrFilename)
  }

  const filename = pathOrFilename.split(/[\\/]/).pop() || pathOrFilename

  return `/api/plugins/blender/files/${encodeURIComponent(filename)}`
}

export function studioDeepLinkHash(params: {
  format?: string
  localPath?: string
  name?: string
  url?: string
}): string {
  const search = new URLSearchParams()

  if (params.localPath) {
    search.set('path', params.localPath)
  }

  if (params.url) {
    search.set('url', params.url)
  }

  if (params.name) {
    search.set('name', params.name)
  }

  if (params.format) {
    search.set('format', params.format)
  }

  const qs = search.toString()

  return qs ? `#/blender?${qs}` : '#/blender'
}

/**
 * Pure parser extracting structured model data from a blender tool result.
 * Returns null if the call failed or produced no 3D/image file deliverable
 * (e.g. `blender_run_script` executed solely for stdout).
 */
export function blenderModelFromResult(result: unknown): BlenderModelResultData | null {
  const record = recordFromUnknown(result)

  if (!record || record.success === false || record.output_exists === false) {
    return null
  }

  const outputPath = typeof record.output_path === 'string' ? record.output_path.trim() : ''
  const rawFilename = typeof record.filename === 'string' ? record.filename.trim() : ''
  const rawUrl = typeof record.url === 'string' ? record.url.trim() : ''

  if (!outputPath && !rawFilename && !rawUrl) {
    return null
  }

  const filename = rawFilename || (outputPath || rawUrl).split(/[\\/]/).pop() || 'model.glb'
  const formatRaw = typeof record.format === 'string' ? record.format : filename
  const format = detectModelFormat(formatRaw.includes('.') ? formatRaw : `x.${formatRaw}`)

  const prompt = typeof record.prompt === 'string' ? record.prompt : ''
  const fileSizeBytes = typeof record.file_size_bytes === 'number' ? record.file_size_bytes : undefined
  const durationSeconds = typeof record.duration_seconds === 'number' ? record.duration_seconds : undefined
  const displayUrl = rawUrl ? resolveModelDisplayUrl(rawUrl) : resolveModelDisplayUrl(outputPath || filename)

  return {
    displayUrl,
    duration_seconds: durationSeconds,
    file_size_bytes: fileSizeBytes,
    filename,
    format,
    output_path: outputPath,
    prompt,
    success: true
  }
}
