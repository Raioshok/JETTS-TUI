import { Button, cn, EmptyState, host, icons, Loader, type PluginContext, Tip, useI18n } from '@jetts-tui/plugin-sdk'
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

const { AlertCircle, Box, Check, ChevronLeft, Download, Eye, Layers3, RefreshCw, Sun, Upload } = icons

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
  const { t } = useI18n()
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
    version: 'Checking…'
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

  // Escape dismisses the PNG render lightbox overlay
  useEffect(() => {
    if (!renderedImageUrl) {
      return
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !event.defaultPrevented) {
        event.preventDefault()
        setRenderedImageUrl(null)
      }
    }

    window.addEventListener('keydown', onKeyDown)

    return () => window.removeEventListener('keydown', onKeyDown)
  }, [renderedImageUrl])

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
        setStatusMessage(`Rendering ${String(evt.filename || 'asset')}…`)
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
    setStatusMessage('Generating 3D model via Blender…')

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

  const handleBackToChat = () => {
    if (window.history.length > 1) {
      window.history.back()

      return
    }

    host.navigate('/')
  }

  const selectLibraryItem = (item: ModelItem) => {
    const assetUrl = resolvePluginAssetUrl({ path: item.path, url: item.url })
    const fmt = normalizeModelFormat(item.format)

    revokePreviousBlobUrl()

    if (fmt === 'png') {
      setRenderedImageUrl(assetUrl)
    } else {
      setModelFormat(fmt)
      setModelUrl(assetUrl)
      setCurrentModelName(item.filename)
      setRenderedImageUrl(null)
    }
  }

  return (
    <div className="flex h-full w-full flex-col overflow-hidden bg-(--ui-bg-chrome) pt-(--titlebar-height,34px) font-sans text-(--ui-text-primary) select-none">
      {/* --- TOP TOOLBAR --- */}
      <header className="flex h-12 shrink-0 items-center justify-between gap-2 border-b border-(--ui-stroke-tertiary) bg-(--ui-bg-sidebar) px-4">
        <div className="flex min-w-0 items-center gap-2.5">
          <Button onClick={handleBackToChat} size="xs" type="button" variant="ghost">
            <ChevronLeft className="size-3.5" />
            <span>{t.common.back}</span>
          </Button>

          <div className="h-4 w-px bg-(--ui-stroke-tertiary)" />

          <div className="flex items-center gap-2">
            <span className="flex size-7 items-center justify-center rounded-lg bg-primary/12 text-primary">
              <Box className="size-4" />
            </span>
            <span className="text-sm font-semibold tracking-tight">Blender 3D Studio</span>
          </div>

          <div className="mx-1 h-4 w-px bg-(--ui-stroke-tertiary)" />

          <div className="hidden items-center gap-1.5 rounded-md border border-(--ui-stroke-tertiary) bg-(--ui-bg-elevated) px-2.5 py-1 font-mono text-xs text-(--ui-text-secondary) sm:flex">
            <span className="size-2 rounded-full bg-(--ui-green)" />
            <span className="max-w-48 truncate">{currentModelName}</span>
          </div>
        </div>

        <div className="flex items-center gap-1 overflow-x-auto">
          <div className="flex items-center rounded-lg border border-(--ui-stroke-tertiary) bg-(--ui-bg-elevated) p-0.5 text-xs">
            {(['textured', 'wireframe', 'normal', 'matcap'] as ShadingMode[]).map(mode => (
              <button
                aria-pressed={shadingMode === mode}
                className={cn(
                  'cursor-pointer rounded px-2 py-1 capitalize transition-colors',
                  shadingMode === mode
                    ? 'bg-primary font-medium text-primary-foreground shadow-xs'
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

          <div className="mx-1 h-4 w-px bg-(--ui-stroke-tertiary)" />

          <div className="flex items-center rounded-lg border border-(--ui-stroke-tertiary) bg-(--ui-bg-elevated) p-0.5 text-xs">
            {(['iso', 'front', 'top', 'side'] as CameraAngle[]).map(angle => (
              <Tip key={angle} label={`Align camera to ${angle} view`}>
                <button
                  className="cursor-pointer rounded px-2 py-1 font-mono text-[0.65rem] text-(--ui-text-tertiary) uppercase transition-colors hover:bg-(--ui-control-hover-background) hover:text-(--ui-text-primary)"
                  onClick={() => viewportRef.current?.resetCamera(angle)}
                  type="button"
                >
                  {angle}
                </button>
              </Tip>
            ))}
          </div>

          <div className="mx-1 h-4 w-px bg-(--ui-stroke-tertiary)" />

          <Tip label="Toggle ground grid">
            <button
              aria-pressed={showGrid}
              className={cn(
                'flex cursor-pointer items-center gap-1 rounded-md border px-2 py-1 text-xs transition-colors',
                showGrid
                  ? 'border-primary/40 bg-primary/12 text-(--ui-text-primary)'
                  : 'border-(--ui-stroke-tertiary) text-(--ui-text-tertiary) hover:text-(--ui-text-primary)'
              )}
              onClick={() => setShowGrid(!showGrid)}
              type="button"
            >
              <Layers3 className="size-3.5" />
              <span>Grid</span>
            </button>
          </Tip>

          <Tip label="Toggle XYZ axes">
            <button
              aria-pressed={showAxes}
              className={cn(
                'flex cursor-pointer items-center gap-1 rounded-md border px-2 py-1 text-xs transition-colors',
                showAxes
                  ? 'border-primary/40 bg-primary/12 text-(--ui-text-primary)'
                  : 'border-(--ui-stroke-tertiary) text-(--ui-text-tertiary) hover:text-(--ui-text-primary)'
              )}
              onClick={() => setShowAxes(!showAxes)}
              type="button"
            >
              <span>XYZ</span>
            </button>
          </Tip>

          <Tip label="Auto-rotate turntable">
            <button
              aria-pressed={autoRotate}
              className={cn(
                'flex cursor-pointer items-center gap-1 rounded-md border px-2 py-1 text-xs transition-colors',
                autoRotate
                  ? 'border-primary/40 bg-primary/12 text-(--ui-text-primary)'
                  : 'border-(--ui-stroke-tertiary) text-(--ui-text-tertiary) hover:text-(--ui-text-primary)'
              )}
              onClick={() => setAutoRotate(!autoRotate)}
              type="button"
            >
              <RefreshCw className={cn('size-3.5', autoRotate && 'animate-spin')} />
              <span>Orbit</span>
            </button>
          </Tip>

          <Tip label="Save viewport snapshot (PNG)">
            <button
              className="flex cursor-pointer items-center gap-1 rounded-md border border-(--ui-stroke-tertiary) bg-(--ui-bg-elevated) px-2.5 py-1 text-xs transition-colors hover:bg-(--ui-control-hover-background)"
              onClick={handleTakeSnapshot}
              type="button"
            >
              <Eye className="size-3.5 text-primary" />
              <span>Capture</span>
            </button>
          </Tip>

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
          <Tip label="Open 3D file (.glb, .gltf, .obj)">
            <button
              className="flex cursor-pointer items-center gap-1 rounded-md border border-(--ui-stroke-tertiary) bg-(--ui-bg-elevated) px-2.5 py-1 text-xs transition-colors hover:bg-(--ui-control-hover-background)"
              onClick={() => fileInputRef.current?.click()}
              type="button"
            >
              <Upload className="size-3.5" />
              <span>Open</span>
            </button>
          </Tip>
        </div>
      </header>

      {/* --- MAIN WORKSPACE AREA --- */}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <div
          className={cn(
            'relative h-full min-w-0 flex-1 bg-[#0c0d12] transition-colors',
            isDragOver && 'ring-2 ring-primary ring-inset'
          )}
          onDragLeave={() => setIsDragOver(false)}
          onDragOver={e => {
            e.preventDefault()
            setIsDragOver(true)
          }}
          onDrop={handleDrop}
        >
          {renderedImageUrl ? (
            <div
              aria-label="Render result"
              className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-black/80 p-6 backdrop-blur-xs"
              onClick={e => {
                if (e.target === e.currentTarget) {
                  setRenderedImageUrl(null)
                }
              }}
              role="dialog"
            >
              <img
                alt="Render Result"
                className="max-h-[80%] max-w-[90%] rounded-xl border border-white/10 object-contain shadow-2xl"
                src={renderedImageUrl}
              />
              <div className="mt-4 flex items-center gap-3">
                <a
                  className="inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-xs font-medium text-primary-foreground shadow-sm transition-colors hover:bg-primary/90"
                  download="blender_render.png"
                  href={renderedImageUrl}
                >
                  <Download className="size-4" />
                  <span>Download Render</span>
                </a>
                <Button onClick={() => setRenderedImageUrl(null)} size="sm" type="button" variant="secondary">
                  Back to 3D Viewport
                </Button>
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

          <div className="absolute bottom-4 left-4 flex items-center gap-3 rounded-lg border border-white/10 bg-black/65 px-3 py-1.5 font-mono text-[0.7rem] text-zinc-300 backdrop-blur-md">
            <div>
              <span className="text-zinc-400">Verts: </span>
              <span className="font-semibold text-white">{stats.vertices.toLocaleString()}</span>
            </div>
            <div className="h-3 w-px bg-white/10" />
            <div>
              <span className="text-zinc-400">Tris: </span>
              <span className="font-semibold text-white">{stats.triangles.toLocaleString()}</span>
            </div>
            <div className="h-3 w-px bg-white/10" />
            <div>
              <span className="text-zinc-400">Meshes: </span>
              <span className="text-zinc-200">{stats.meshes}</span>
            </div>
          </div>

          <div className="absolute right-4 bottom-4 flex items-center gap-2 rounded-lg border border-white/10 bg-black/65 px-3 py-1.5 text-[0.68rem] text-zinc-300 backdrop-blur-md">
            <span>
              Rotate: <b className="text-white">Left-Drag</b>
            </span>
            <span>
              • Pan: <b className="text-white">Right-Drag</b>
            </span>
            <span>
              • Zoom: <b className="text-white">Wheel</b>
            </span>
          </div>

          {isDragOver && (
            <div className="pointer-events-none absolute inset-0 z-30 flex items-center justify-center bg-black/55 backdrop-blur-xs">
              <div className="flex flex-col items-center gap-2 rounded-2xl border-2 border-dashed border-primary bg-black/80 p-8 shadow-2xl">
                <Box className="size-12 text-primary" />
                <span className="text-base font-semibold text-white">Drop 3D Model to Inspect</span>
                <span className="text-xs text-zinc-300">Supports .glb, .gltf, .obj</span>
              </div>
            </div>
          )}
        </div>

        {/* --- RIGHT SIDEBAR: GENERATOR & LIBRARY --- */}
        <aside className="flex w-80 shrink-0 flex-col overflow-hidden border-l border-(--ui-stroke-tertiary) bg-(--ui-bg-sidebar)">
          <div className="flex border-b border-(--ui-stroke-tertiary)">
            <button
              className={cn(
                'flex-1 cursor-pointer border-b-2 py-2.5 text-center text-xs font-medium transition-colors',
                activeTab === 'generate'
                  ? 'border-primary bg-primary/8 font-semibold text-(--ui-text-primary)'
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
                  ? 'border-primary bg-primary/8 font-semibold text-(--ui-text-primary)'
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
                  <span className="text-[0.68rem] text-primary">Blender bpy</span>
                </label>
                <textarea
                  className="h-24 w-full resize-none rounded-lg border border-(--ui-stroke-tertiary) bg-(--ui-bg-editor) p-2.5 text-xs leading-relaxed text-(--ui-text-primary) placeholder:text-(--ui-text-quaternary) focus:border-primary focus:outline-hidden"
                  onChange={e => setPrompt(e.target.value)}
                  placeholder="Describe the 3D model, prop, or architecture to create…"
                  value={prompt}
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-(--ui-text-secondary)">Archetype Preset</label>
                <div className="grid grid-cols-2 gap-1.5">
                  {(
                    [
                      { id: 'nature', label: 'Nature' },
                      { id: 'scifi', label: 'Sci-Fi' },
                      { id: 'architecture', label: 'Building' },
                      { id: 'furniture', label: 'Furniture' },
                      { id: 'abstract', label: 'Sculpture' },
                      { id: 'auto', label: 'Auto-Detect' }
                    ] as const
                  ).map(item => (
                    <button
                      aria-pressed={preset === item.id}
                      className={cn(
                        'flex cursor-pointer items-center justify-center rounded-md border px-2 py-1.5 text-xs transition-colors',
                        preset === item.id
                          ? 'border-primary/60 bg-primary/12 font-medium text-(--ui-text-primary)'
                          : 'border-(--ui-stroke-tertiary) bg-(--ui-bg-elevated) text-(--ui-text-secondary) hover:bg-(--ui-control-hover-background)'
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
                    className="w-full rounded-md border border-(--ui-stroke-tertiary) bg-(--ui-bg-editor) px-2 py-1.5 text-xs text-(--ui-text-primary) focus:outline-hidden"
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
                    className="w-full rounded-md border border-(--ui-stroke-tertiary) bg-(--ui-bg-editor) px-2 py-1.5 text-xs text-(--ui-text-primary) focus:outline-hidden"
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
                    <Sun className="size-3 text-(--ui-yellow)" />
                    <span>Studio Lighting</span>
                  </span>
                  <span>{Math.round(lightIntensity * 100)}%</span>
                </div>
                <input
                  aria-label="Studio Lighting"
                  className="w-full cursor-pointer accent-primary"
                  max="2.5"
                  min="0.2"
                  onChange={e => setLightIntensity(parseFloat(e.target.value))}
                  step="0.1"
                  type="range"
                  value={lightIntensity}
                />
              </div>

              <Button
                className="w-full"
                disabled={isGenerating || !prompt.trim()}
                onClick={() => void handleGenerate()}
                type="button"
              >
                {isGenerating ? (
                  <>
                    <Loader className="size-4" />
                    <span>Running Blender Engine…</span>
                  </>
                ) : (
                  <>
                    <Box className="size-4" />
                    <span>Generate in Blender</span>
                  </>
                )}
              </Button>

              {statusMessage && (
                <div className="flex items-center gap-2 rounded-md border border-(--ui-green)/25 bg-(--ui-green)/10 p-2 text-xs text-(--ui-green)">
                  <Check className="size-3.5 shrink-0" />
                  <span>{statusMessage}</span>
                </div>
              )}

              {errorMessage && (
                <div className="flex items-start gap-2 rounded-md border border-(--ui-red)/25 bg-(--ui-red)/10 p-2 text-xs text-(--ui-red)">
                  <AlertCircle className="mt-0.5 size-3.5 shrink-0" />
                  <span className="break-words">{errorMessage}</span>
                </div>
              )}

              <div className="mt-4 space-y-2 rounded-lg border border-(--ui-stroke-tertiary) bg-(--ui-bg-elevated) p-3 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-[0.7rem] font-semibold tracking-wider text-(--ui-text-tertiary) uppercase">
                    Blender Environment
                  </span>
                  <span
                    className={cn(
                      'size-2 rounded-full',
                      blenderStatus.available ? 'bg-(--ui-green)' : 'bg-(--ui-yellow)'
                    )}
                  />
                </div>
                <div className="font-mono text-[0.75rem] text-(--ui-text-secondary)">{blenderStatus.version}</div>
                {blenderStatus.path && (
                  <div className="truncate font-mono text-[0.65rem] text-(--ui-text-quaternary)">
                    {blenderStatus.path}
                  </div>
                )}
                {!blenderStatus.available && (
                  <p className="text-[0.7rem] leading-relaxed text-(--ui-text-secondary)">
                    Install Blender from{' '}
                    <a
                      className="font-semibold text-primary underline"
                      href="https://www.blender.org/download/"
                      rel="noreferrer"
                      target="_blank"
                    >
                      blender.org
                    </a>{' '}
                    to generate new models. Previews of local models are always interactive.
                  </p>
                )}
              </div>
            </div>
          )}

          {activeTab === 'library' && (
            <div className="flex-1 space-y-2 overflow-y-auto p-3">
              <div className="flex items-center justify-between px-1 text-xs text-(--ui-text-secondary)">
                <span>Recent Assets</span>
                <Tip label={t.common.refresh}>
                  <Button
                    aria-label={t.common.refresh}
                    className="size-6 p-0"
                    onClick={() => void fetchStatusAndModels()}
                    size="icon"
                    type="button"
                    variant="ghost"
                  >
                    <RefreshCw className="size-3" />
                  </Button>
                </Tip>
              </div>

              {modelsList.length === 0 ? (
                <EmptyState description="Generate your first model in the Generate 3D tab." title="No models yet" />
              ) : (
                modelsList.map(item => {
                  const assetUrl = resolvePluginAssetUrl({ path: item.path, url: item.url })

                  return (
                    <div
                      className={cn(
                        'flex cursor-pointer items-center justify-between rounded-lg border border-(--ui-stroke-tertiary) bg-(--ui-bg-elevated) p-2.5 transition-colors hover:bg-(--ui-control-hover-background) focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-hidden',
                        currentModelName === item.filename && 'border-primary/70 bg-primary/10'
                      )}
                      key={item.filename}
                      onClick={() => selectLibraryItem(item)}
                      onKeyDown={e => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          selectLibraryItem(item)
                        }
                      }}
                      role="button"
                      tabIndex={0}
                    >
                      <div className="flex min-w-0 items-center gap-2.5">
                        <span className="flex size-7 shrink-0 items-center justify-center rounded bg-primary/12 text-primary">
                          <Box className="size-3.5" />
                        </span>
                        <div className="min-w-0">
                          <div className="truncate text-xs font-medium text-(--ui-text-primary)">{item.filename}</div>
                          <div className="font-mono text-[0.68rem] text-(--ui-text-tertiary)">
                            {(item.size_bytes / 1024).toFixed(1)} KB • {item.format.toUpperCase()}
                          </div>
                        </div>
                      </div>
                      <Tip label="Download file">
                        <a
                          aria-label={`Download ${item.filename}`}
                          className="rounded p-1 text-(--ui-text-tertiary) transition-colors hover:bg-(--ui-control-hover-background) hover:text-(--ui-text-primary)"
                          download={item.filename}
                          href={assetUrl}
                          onClick={e => e.stopPropagation()}
                        >
                          <Download className="size-3.5" />
                        </a>
                      </Tip>
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
