import { cn, icons, type PluginContext } from '@jetts-tui/plugin-sdk'
import type React from 'react'
import { useCallback, useEffect, useRef, useState } from 'react'

import type {
  BlenderStatus,
  CameraAngle,
  GenerateResponse,
  ModelFileFormat,
  ModelItem,
  ModelStats,
  OutputFormat,
  RenderPreset,
  RenderQuality,
  ShadingMode
} from './types'
import { BlenderViewport, type ViewportHandle } from './viewport'

const { AlertCircle, Box, Check, Download, Eye, Layers3, RefreshCw, Sun, Upload } = icons

function normalizeModelFormat(raw?: null | string): ModelFileFormat {
  const lower = (raw || '').toLowerCase().trim()

  if (lower === 'obj') {
    return 'obj'
  }

  if (lower === 'gltf') {
    return 'gltf'
  }

  if (lower === 'png') {
    return 'png'
  }

  return 'glb'
}

function resolvePluginAssetUrl(item: { path?: null | string; url?: null | string }): string {
  const rawPath = item.path?.trim() || ''

  if (rawPath && typeof window !== 'undefined' && 'jettstuiDesktop' in window) {
    const cleanPath = rawPath.replace(/^file:\/\//i, '')

    return `jettstui-media://stream/${encodeURIComponent(cleanPath)}`
  }

  return item.url || ''
}

export function BlenderStudioView({ ctx }: { ctx: PluginContext }) {
  const viewportRef = useRef<ViewportHandle>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const blobUrlRef = useRef<null | string>(null)

  const [modelUrl, setModelUrl] = useState<null | string>(null)
  const [modelFormat, setModelFormat] = useState<ModelFileFormat>('glb')
  const [currentModelName, setCurrentModelName] = useState<string>('Procedural Sculpture')
  const [shadingMode, setShadingMode] = useState<ShadingMode>('textured')
  const [showGrid, setShowGrid] = useState(true)
  const [showAxes, setShowAxes] = useState(false)
  const [autoRotate, setAutoRotate] = useState(false)
  const [lightIntensity, setLightIntensity] = useState(1.0)
  const [stats, setStats] = useState<ModelStats>({ meshes: 1, triangles: 3200, vertices: 1600 })
  const [isDragOver, setIsDragOver] = useState(false)

  const [prompt, setPrompt] = useState('A stylized low-poly pine forest with campfire and stones')
  const [preset, setPreset] = useState<RenderPreset>('nature')
  const [quality, setQuality] = useState<RenderQuality>('draft')
  const [outputFormat, setOutputFormat] = useState<OutputFormat>('glb')
  const [isGenerating, setIsGenerating] = useState(false)
  const [renderedImageUrl, setRenderedImageUrl] = useState<null | string>(null)
  const [statusMessage, setStatusMessage] = useState<null | string>(null)
  const [errorMessage, setErrorMessage] = useState<null | string>(null)

  const [blenderStatus, setBlenderStatus] = useState<BlenderStatus>({
    available: false,
    path: null,
    version: 'Checking...'
  })

  const [modelsList, setModelsList] = useState<ModelItem[]>([])
  const [activeTab, setActiveTab] = useState<'generate' | 'library'>('generate')

  const revokePreviousBlobUrl = useCallback(() => {
    if (blobUrlRef.current) {
      URL.revokeObjectURL(blobUrlRef.current)
      blobUrlRef.current = null
    }
  }, [])

  useEffect(() => {
    return () => {
      revokePreviousBlobUrl()
    }
  }, [revokePreviousBlobUrl])

  // Adopt deep-linked model from `#/blender?path=...&url=...&name=...&format=...`
  useEffect(() => {
    const syncFromHash = () => {
      const hash = window.location.hash || ''
      const queryIdx = hash.indexOf('?')

      if (queryIdx === -1) {
        return
      }

      const params = new URLSearchParams(hash.slice(queryIdx + 1))
      const linkedPath = params.get('path')
      const linkedUrl = params.get('url')
      const linkedName = params.get('name')
      const linkedFormat = normalizeModelFormat(params.get('format'))
      const resolved = resolvePluginAssetUrl({ path: linkedPath, url: linkedUrl })

      if (!resolved) {
        return
      }

      revokePreviousBlobUrl()

      if (linkedName) {
        setCurrentModelName(linkedName)
      }

      if (linkedFormat === 'png') {
        setRenderedImageUrl(resolved)
      } else {
        setModelFormat(linkedFormat)
        setModelUrl(resolved)
        setRenderedImageUrl(null)
      }
    }

    syncFromHash()
    window.addEventListener('hashchange', syncFromHash)

    return () => {
      window.removeEventListener('hashchange', syncFromHash)
    }
  }, [revokePreviousBlobUrl])

  const fetchStatusAndModels = useCallback(async () => {
    try {
      const data = await ctx.rest<BlenderStatus>('/status')
      setBlenderStatus(data)
    } catch {
      setBlenderStatus({
        available: false,
        path: null,
        version: 'Backend offline'
      })
    }

    try {
      const data = await ctx.rest<{ models?: ModelItem[] }>('/models')
      setModelsList(data.models || [])
    } catch {
      // Ignore transient load errors
    }
  }, [ctx])

  useEffect(() => {
    void fetchStatusAndModels()

    const disposeSocket = ctx.socket('/events', payload => {
      if (!payload || typeof payload !== 'object') {
        return
      }

      const evt = payload as Record<string, unknown>

      if (evt.type === 'render_start') {
        setStatusMessage(`Rendering ${String(evt.filename || 'asset')}...`)
      } else if (evt.type === 'render_complete') {
        void fetchStatusAndModels()
      }
    })

    return () => {
      disposeSocket()
    }
  }, [ctx, fetchStatusAndModels])

  const handleGenerate = async () => {
    if (!prompt.trim()) {
      return
    }

    setIsGenerating(true)
    setErrorMessage(null)
    setStatusMessage('Generating 3D model via Blender...')

    try {
      const result = await ctx.rest<GenerateResponse>('/generate', {
        body: {
          format: outputFormat,
          preset,
          prompt: prompt.trim(),
          quality
        },
        method: 'POST',
        timeoutMs: 130_000
      })

      setStatusMessage(`Complete in ${result.duration_seconds}s`)
      const assetUrl = resolvePluginAssetUrl({ path: result.path, url: result.url })
      const fmt = normalizeModelFormat(result.format)

      revokePreviousBlobUrl()

      if (fmt === 'png') {
        setRenderedImageUrl(assetUrl)
      } else {
        setModelFormat(fmt)
        setModelUrl(assetUrl)
        setCurrentModelName(result.filename)
        setRenderedImageUrl(null)
      }

      void fetchStatusAndModels()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to generate 3D model'
      setErrorMessage(msg)
      setStatusMessage(null)
    } finally {
      setIsGenerating(false)
    }
  }

  const handleFileUpload = (file: File) => {
    const ext = file.name.split('.').pop()?.toLowerCase()

    if (!ext || !['glb', 'gltf', 'obj'].includes(ext)) {
      setErrorMessage('Please provide a .glb, .gltf, or .obj 3D model file')

      return
    }

    revokePreviousBlobUrl()
    const objectUrl = URL.createObjectURL(file)
    blobUrlRef.current = objectUrl

    setErrorMessage(null)
    setModelFormat(normalizeModelFormat(ext))
    setModelUrl(objectUrl)
    setCurrentModelName(file.name)
    setRenderedImageUrl(null)
    setStatusMessage(`Loaded local file: ${file.name}`)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(false)

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileUpload(e.dataTransfer.files[0])
    }
  }

  const handleTakeSnapshot = () => {
    if (!viewportRef.current) {
      return
    }

    const dataUrl = viewportRef.current.takeSnapshot()

    if (!dataUrl) {
      return
    }

    const link = document.createElement('a')
    link.download = `${currentModelName}_snapshot.png`
    link.href = dataUrl
    link.click()
  }

  return (
    <div className="flex h-full w-full flex-col overflow-hidden bg-(--ui-background) font-sans text-(--ui-text-primary) select-none">
      {/* --- TOP TOOLBAR --- */}
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-(--ui-border) bg-(--ui-panel-background)/60 px-4 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="flex size-7 items-center justify-center rounded-lg border border-violet-500/30 bg-violet-600/20 text-violet-400">
              <Box className="size-4" />
            </span>
            <span className="text-sm font-semibold tracking-wide">Blender 3D Studio</span>
          </div>

          <div className="mx-1 h-4 w-px bg-(--ui-border)" />

          <div className="flex items-center gap-1.5 rounded-md border border-(--ui-border)/60 bg-(--ui-surface-background)/80 px-2.5 py-1 font-mono text-xs text-(--ui-text-secondary)">
            <span className="size-2 animate-pulse rounded-full bg-emerald-500" />
            <span className="max-w-[200px] truncate">{currentModelName}</span>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <div className="flex items-center rounded-lg border border-(--ui-border) bg-(--ui-surface-background) p-0.5 text-xs">
            {(['textured', 'wireframe', 'normal', 'matcap'] as ShadingMode[]).map(mode => (
              <button
                className={cn(
                  'cursor-pointer rounded px-2 py-1 capitalize transition-all',
                  shadingMode === mode
                    ? 'bg-violet-600 font-medium text-white shadow-xs'
                    : 'text-(--ui-text-tertiary) hover:text-(--ui-text-primary)'
                )}
                key={mode}
                onClick={() => setShadingMode(mode)}
                type="button"
              >
                {mode}
              </button>
            ))}
          </div>

          <div className="mx-1 h-4 w-px bg-(--ui-border)" />

          <div className="flex items-center rounded-lg border border-(--ui-border) bg-(--ui-surface-background) p-0.5 text-xs">
            {(['iso', 'front', 'top', 'side'] as CameraAngle[]).map(angle => (
              <button
                className="cursor-pointer rounded px-2 py-1 font-mono text-[0.65rem] text-(--ui-text-tertiary) uppercase hover:bg-(--ui-hover) hover:text-(--ui-text-primary)"
                key={angle}
                onClick={() => viewportRef.current?.resetCamera(angle)}
                title={`Align camera to ${angle} view`}
                type="button"
              >
                {angle}
              </button>
            ))}
          </div>

          <div className="mx-1 h-4 w-px bg-(--ui-border)" />

          <button
            className={cn(
              'flex cursor-pointer items-center gap-1 rounded-md border px-2 py-1 text-xs transition-colors',
              showGrid
                ? 'border-violet-500/40 bg-violet-500/10 text-violet-300'
                : 'border-(--ui-border) text-(--ui-text-tertiary) hover:text-(--ui-text-primary)'
            )}
            onClick={() => setShowGrid(!showGrid)}
            title="Toggle Ground Grid"
            type="button"
          >
            <Layers3 className="size-3.5" />
            <span>Grid</span>
          </button>

          <button
            className={cn(
              'flex cursor-pointer items-center gap-1 rounded-md border px-2 py-1 text-xs transition-colors',
              showAxes
                ? 'border-violet-500/40 bg-violet-500/10 text-violet-300'
                : 'border-(--ui-border) text-(--ui-text-tertiary) hover:text-(--ui-text-primary)'
            )}
            onClick={() => setShowAxes(!showAxes)}
            title="Toggle XYZ Axes"
            type="button"
          >
            <span>XYZ</span>
          </button>

          <button
            className={cn(
              'flex cursor-pointer items-center gap-1 rounded-md border px-2 py-1 text-xs transition-colors',
              autoRotate
                ? 'border-violet-500/40 bg-violet-500/10 text-violet-300'
                : 'border-(--ui-border) text-(--ui-text-tertiary) hover:text-(--ui-text-primary)'
            )}
            onClick={() => setAutoRotate(!autoRotate)}
            title="Auto Rotate Turntable"
            type="button"
          >
            <RefreshCw className={cn('size-3.5', autoRotate && 'animate-spin')} />
            <span>Orbit</span>
          </button>

          <button
            className="flex cursor-pointer items-center gap-1 rounded-md border border-(--ui-border) bg-(--ui-surface-background) px-2.5 py-1 text-xs hover:bg-(--ui-hover)"
            onClick={handleTakeSnapshot}
            title="Take Viewport Snapshot (PNG)"
            type="button"
          >
            <Eye className="size-3.5 text-violet-400" />
            <span>Capture</span>
          </button>

          <input
            accept=".glb,.gltf,.obj"
            className="hidden"
            onChange={e => {
              if (e.target.files && e.target.files[0]) {
                handleFileUpload(e.target.files[0])
              }
            }}
            ref={fileInputRef}
            type="file"
          />
          <button
            className="flex cursor-pointer items-center gap-1 rounded-md border border-(--ui-border) bg-(--ui-surface-background) px-2.5 py-1 text-xs hover:bg-(--ui-hover)"
            onClick={() => fileInputRef.current?.click()}
            title="Open 3D File (.glb, .gltf, .obj)"
            type="button"
          >
            <Upload className="size-3.5" />
            <span>Open</span>
          </button>
        </div>
      </header>

      {/* --- MAIN WORKSPACE AREA --- */}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <div
          className={cn(
            'relative h-full min-w-0 flex-1 bg-[#0c0d12] transition-all',
            isDragOver && 'bg-violet-950/20 ring-2 ring-violet-500 ring-inset'
          )}
          onDragLeave={() => setIsDragOver(false)}
          onDragOver={e => {
            e.preventDefault()
            setIsDragOver(true)
          }}
          onDrop={handleDrop}
        >
          {renderedImageUrl ? (
            <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-black/80 p-6 backdrop-blur-xs">
              <img
                alt="Render Result"
                className="max-h-[80%] max-w-[90%] rounded-xl border border-white/10 object-contain shadow-2xl"
                src={renderedImageUrl}
              />
              <div className="mt-4 flex items-center gap-3">
                <a
                  className="flex items-center gap-1.5 rounded-lg bg-violet-600 px-4 py-2 text-xs font-medium text-white shadow-lg transition-all hover:bg-violet-500"
                  download="blender_render.png"
                  href={renderedImageUrl}
                >
                  <Download className="size-4" />
                  <span>Download Render</span>
                </a>
                <button
                  className="rounded-lg border border-(--ui-border) bg-(--ui-surface-background) px-4 py-2 text-xs hover:bg-(--ui-hover)"
                  onClick={() => setRenderedImageUrl(null)}
                  type="button"
                >
                  Back to 3D Viewport
                </button>
              </div>
            </div>
          ) : null}

          <BlenderViewport
            autoRotate={autoRotate}
            lightIntensity={lightIntensity}
            modelFormat={modelFormat}
            modelUrl={modelUrl}
            onError={err => setErrorMessage(err)}
            onStatsChange={setStats}
            ref={viewportRef}
            shadingMode={shadingMode}
            showAxes={showAxes}
            showGrid={showGrid}
          />

          <div className="absolute bottom-4 left-4 flex items-center gap-3 rounded-lg border border-white/10 bg-black/60 px-3 py-1.5 font-mono text-[0.7rem] text-zinc-400 backdrop-blur-md">
            <div>
              <span className="text-zinc-500">Verts: </span>
              <span className="font-semibold text-violet-400">{stats.vertices.toLocaleString()}</span>
            </div>
            <div className="h-3 w-px bg-white/10" />
            <div>
              <span className="text-zinc-500">Tris: </span>
              <span className="font-semibold text-violet-400">{stats.triangles.toLocaleString()}</span>
            </div>
            <div className="h-3 w-px bg-white/10" />
            <div>
              <span className="text-zinc-500">Meshes: </span>
              <span className="text-zinc-200">{stats.meshes}</span>
            </div>
          </div>

          <div className="absolute right-4 bottom-4 flex items-center gap-2 rounded-lg border border-white/10 bg-black/60 px-3 py-1.5 text-[0.68rem] text-zinc-400 backdrop-blur-md">
            <span>
              Rotate: <b className="text-zinc-200">Left-Drag</b>
            </span>
            <span>
              • Pan: <b className="text-zinc-200">Right-Drag</b>
            </span>
            <span>
              • Zoom: <b className="text-zinc-200">Wheel</b>
            </span>
          </div>

          {isDragOver && (
            <div className="pointer-events-none absolute inset-0 z-30 flex items-center justify-center bg-violet-950/40 backdrop-blur-xs">
              <div className="flex flex-col items-center gap-2 rounded-2xl border-2 border-dashed border-violet-400 bg-black/70 p-8 shadow-2xl">
                <Box className="size-12 animate-bounce text-violet-400" />
                <span className="text-base font-semibold text-white">Drop 3D Model to Inspect</span>
                <span className="text-xs text-zinc-400">Supports .glb, .gltf, .obj</span>
              </div>
            </div>
          )}
        </div>

        {/* --- RIGHT SIDEBAR: GENERATOR & LIBRARY --- */}
        <aside className="flex w-80 shrink-0 flex-col overflow-hidden border-l border-(--ui-border) bg-(--ui-panel-background)/40">
          <div className="flex border-b border-(--ui-border)">
            <button
              className={cn(
                'flex-1 cursor-pointer border-b-2 py-2.5 text-center text-xs font-medium transition-colors',
                activeTab === 'generate'
                  ? 'border-violet-500 bg-violet-500/5 font-semibold text-violet-400'
                  : 'border-transparent text-(--ui-text-secondary) hover:text-(--ui-text-primary)'
              )}
              onClick={() => setActiveTab('generate')}
              type="button"
            >
              Generate 3D
            </button>
            <button
              className={cn(
                'flex-1 cursor-pointer border-b-2 py-2.5 text-center text-xs font-medium transition-colors',
                activeTab === 'library'
                  ? 'border-violet-500 bg-violet-500/5 font-semibold text-violet-400'
                  : 'border-transparent text-(--ui-text-secondary) hover:text-(--ui-text-primary)'
              )}
              onClick={() => setActiveTab('library')}
              type="button"
            >
              Models Library ({modelsList.length})
            </button>
          </div>

          {activeTab === 'generate' && (
            <div className="flex-1 space-y-4 overflow-y-auto p-4">
              <div className="space-y-1.5">
                <label className="flex items-center justify-between text-xs font-semibold text-(--ui-text-secondary)">
                  <span>Prompt Description</span>
                  <span className="text-[0.68rem] text-violet-400">Blender bpy</span>
                </label>
                <textarea
                  className="h-24 w-full resize-none rounded-lg border border-(--ui-border) bg-(--ui-surface-background) p-2.5 text-xs leading-relaxed text-(--ui-text-primary) placeholder:text-(--ui-text-quaternary) focus:border-violet-500 focus:outline-hidden"
                  onChange={e => setPrompt(e.target.value)}
                  placeholder="Describe the 3D model, prop, or architecture to create..."
                  value={prompt}
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-(--ui-text-secondary)">Archetype Preset</label>
                <div className="grid grid-cols-2 gap-1.5">
                  {(
                    [
                      { id: 'nature', label: '🌲 Nature' },
                      { id: 'scifi', label: '🚀 Sci-Fi' },
                      { id: 'architecture', label: '🏛️ Building' },
                      { id: 'furniture', label: '🪑 Furniture' },
                      { id: 'abstract', label: '🔮 Sculpture' },
                      { id: 'auto', label: '✨ Auto-Detect' }
                    ] as const
                  ).map(item => (
                    <button
                      className={cn(
                        'flex cursor-pointer items-center justify-center rounded-md border px-2 py-1.5 text-xs transition-all',
                        preset === item.id
                          ? 'border-violet-500 bg-violet-500/15 font-medium text-violet-300'
                          : 'border-(--ui-border) bg-(--ui-surface-background)/50 text-(--ui-text-secondary) hover:bg-(--ui-hover)'
                      )}
                      key={item.id}
                      onClick={() => setPreset(item.id)}
                      type="button"
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <label className="text-[0.7rem] font-semibold text-(--ui-text-secondary)">Output Format</label>
                  <select
                    className="w-full rounded-md border border-(--ui-border) bg-(--ui-surface-background) px-2 py-1.5 text-xs focus:outline-hidden"
                    onChange={e => setOutputFormat(e.target.value as OutputFormat)}
                    value={outputFormat}
                  >
                    <option value="glb">GLB (3D Model)</option>
                    <option value="png">PNG (Render)</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <label className="text-[0.7rem] font-semibold text-(--ui-text-secondary)">Engine Quality</label>
                  <select
                    className="w-full rounded-md border border-(--ui-border) bg-(--ui-surface-background) px-2 py-1.5 text-xs focus:outline-hidden"
                    onChange={e => setQuality(e.target.value as RenderQuality)}
                    value={quality}
                  >
                    <option value="draft">Draft (EEVEE)</option>
                    <option value="final">Final (Cycles)</option>
                  </select>
                </div>
              </div>

              <div className="space-y-1 pt-1">
                <div className="flex justify-between text-[0.7rem] text-(--ui-text-secondary)">
                  <span className="flex items-center gap-1">
                    <Sun className="size-3 text-amber-400" />
                    <span>Studio Lighting</span>
                  </span>
                  <span>{Math.round(lightIntensity * 100)}%</span>
                </div>
                <input
                  className="w-full cursor-pointer accent-violet-500"
                  max="2.5"
                  min="0.2"
                  onChange={e => setLightIntensity(parseFloat(e.target.value))}
                  step="0.1"
                  type="range"
                  value={lightIntensity}
                />
              </div>

              <button
                className={cn(
                  'flex w-full cursor-pointer items-center justify-center gap-2 rounded-lg py-2.5 text-xs font-semibold text-white shadow-lg transition-all',
                  isGenerating
                    ? 'cursor-not-allowed bg-violet-700/60'
                    : 'bg-violet-600 hover:bg-violet-500 active:scale-[0.98]'
                )}
                disabled={isGenerating || !prompt.trim()}
                onClick={() => void handleGenerate()}
                type="button"
              >
                {isGenerating ? (
                  <>
                    <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                    <span>Running Blender Engine...</span>
                  </>
                ) : (
                  <>
                    <Box className="size-4" />
                    <span>Generate in Blender</span>
                  </>
                )}
              </button>

              {statusMessage && (
                <div className="flex items-center gap-2 rounded-md border border-emerald-500/20 bg-emerald-500/10 p-2 text-xs text-emerald-400">
                  <Check className="size-3.5 shrink-0" />
                  <span>{statusMessage}</span>
                </div>
              )}

              {errorMessage && (
                <div className="flex items-start gap-2 rounded-md border border-rose-500/20 bg-rose-500/10 p-2 text-xs text-rose-400">
                  <AlertCircle className="mt-0.5 size-3.5 shrink-0" />
                  <span className="break-words">{errorMessage}</span>
                </div>
              )}

              <div className="mt-4 space-y-2 rounded-lg border border-(--ui-border) bg-(--ui-surface-background)/40 p-3 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-[0.7rem] font-semibold tracking-wider text-(--ui-text-tertiary) uppercase">
                    Blender Environment
                  </span>
                  <span
                    className={cn(
                      'size-2 rounded-full',
                      blenderStatus.available ? 'bg-emerald-500' : 'bg-amber-500'
                    )}
                  />
                </div>
                <div className="font-mono text-[0.75rem] text-(--ui-text-secondary)">{blenderStatus.version}</div>
                {blenderStatus.path && (
                  <div className="truncate font-mono text-[0.65rem] text-(--ui-text-quaternary)" title={blenderStatus.path}>
                    {blenderStatus.path}
                  </div>
                )}
                {!blenderStatus.available && (
                  <p className="text-[0.7rem] leading-relaxed text-amber-400/90">
                    Install Blender from{' '}
                    <a
                      className="font-semibold underline"
                      href="https://www.blender.org/download/"
                      rel="noreferrer"
                      target="_blank"
                    >
                      blender.org
                    </a>{' '}
                    to generate new models. Previews of local models are always interactive!
                  </p>
                )}
              </div>
            </div>
          )}

          {activeTab === 'library' && (
            <div className="flex-1 space-y-2 overflow-y-auto p-3">
              <div className="flex items-center justify-between px-1 text-xs text-(--ui-text-secondary)">
                <span>Recent Assets</span>
                <button
                  className="cursor-pointer rounded p-1 hover:text-(--ui-text-primary)"
                  onClick={() => void fetchStatusAndModels()}
                  title="Refresh library"
                  type="button"
                >
                  <RefreshCw className="size-3" />
                </button>
              </div>

              {modelsList.length === 0 ? (
                <div className="flex flex-col items-center justify-center p-8 text-center text-xs text-(--ui-text-tertiary)">
                  <Box className="mb-2 size-8 text-zinc-600" />
                  <span>No models generated yet</span>
                  <span className="mt-1 text-[0.7rem] text-zinc-500">Generate your first model above!</span>
                </div>
              ) : (
                modelsList.map(item => {
                  const assetUrl = resolvePluginAssetUrl({ path: item.path, url: item.url })
                  const fmt = normalizeModelFormat(item.format)

                  return (
                    <div
                      className={cn(
                        'flex cursor-pointer items-center justify-between rounded-lg border border-(--ui-border) bg-(--ui-surface-background)/60 p-2.5 transition-all hover:bg-(--ui-hover)',
                        currentModelName === item.filename && 'border-violet-500/80 bg-violet-500/10'
                      )}
                      key={item.filename}
                      onClick={() => {
                        revokePreviousBlobUrl()

                        if (fmt === 'png') {
                          setRenderedImageUrl(assetUrl)
                        } else {
                          setModelFormat(fmt)
                          setModelUrl(assetUrl)
                          setCurrentModelName(item.filename)
                          setRenderedImageUrl(null)
                        }
                      }}
                    >
                      <div className=" flex min-w-0 items-center gap-2.5">
                        <span className="flex size-7 shrink-0 items-center justify-center rounded bg-violet-500/10 text-violet-400">
                          <Box className="size-3.5" />
                        </span>
                        <div className="min-w-0">
                          <div className="truncate text-xs font-medium text-(--ui-text-primary)">{item.filename}</div>
                          <div className="font-mono text-[0.68rem] text-(--ui-text-tertiary)">
                            {(item.size_bytes / 1024).toFixed(1)} KB • {item.format.toUpperCase()}
                          </div>
                        </div>
                      </div>
                      <a
                        className="p-1 text-(--ui-text-tertiary) hover:text-(--ui-text-primary)"
                        download={item.filename}
                        href={assetUrl}
                        onClick={e => e.stopPropagation()}
                        title="Download file"
                      >
                        <Download className="size-3.5" />
                      </a>
                    </div>
                  )
                })
              )}
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}
