import React, { useState, useEffect, useRef, useCallback } from 'react'
import {
  Box,
  Download,
  Eye,
  RefreshCw,
  Sun,
  Layers3,
  SlidersHorizontal,
  Upload,
  Check,
  AlertCircle
} from '@/lib/icons'
import { cn } from '@/lib/utils'

import { BlenderViewport, type ViewportHandle } from './viewport'
import type {
  BlenderStatus,
  CameraAngle,
  ModelItem,
  ModelStats,
  OutputFormat,
  RenderPreset,
  RenderQuality,
  ShadingMode
} from './types'

export function BlenderStudioView() {
  const viewportRef = useRef<ViewportHandle>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Viewer controls
  const [modelUrl, setModelUrl] = useState<string | null>(null)
  const [currentModelName, setCurrentModelName] = useState<string>('Procedural Sculpture')
  const [shadingMode, setShadingMode] = useState<ShadingMode>('textured')
  const [showGrid, setShowGrid] = useState(true)
  const [showAxes, setShowAxes] = useState(false)
  const [autoRotate, setAutoRotate] = useState(false)
  const [lightIntensity, setLightIntensity] = useState(1.0)
  const [stats, setStats] = useState<ModelStats>({ vertices: 1600, triangles: 3200, meshes: 1 })
  const [isDragOver, setIsDragOver] = useState(false)

  // Generator & Studio State
  const [prompt, setPrompt] = useState('A stylized low-poly pine forest with campfire and stones')
  const [preset, setPreset] = useState<RenderPreset>('nature')
  const [quality, setQuality] = useState<RenderQuality>('draft')
  const [outputFormat, setOutputFormat] = useState<OutputFormat>('glb')
  const [isGenerating, setIsGenerating] = useState(false)
  const [renderedImageUrl, setRenderedImageUrl] = useState<string | null>(null)
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  // Backend state
  const [blenderStatus, setBlenderStatus] = useState<BlenderStatus>({
    available: false,
    version: 'Checking...',
    path: null
  })
  const [modelsList, setModelsList] = useState<ModelItem[]>([])
  const [activeTab, setActiveTab] = useState<'generate' | 'library'>('generate')

  // Fetch Blender backend status and models
  const fetchStatusAndModels = useCallback(async () => {
    try {
      const res = await fetch('/api/plugins/blender/status')
      if (res.ok) {
        const data = await res.json()
        setBlenderStatus(data)
      }
    } catch {
      setBlenderStatus({
        available: false,
        version: 'Backend offline',
        path: null
      })
    }

    try {
      const res = await fetch('/api/plugins/blender/models')
      if (res.ok) {
        const data = await res.json()
        setModelsList(data.models || [])
      }
    } catch {
      // ignore
    }
  }, [])

  useEffect(() => {
    void fetchStatusAndModels()
  }, [fetchStatusAndModels])

  // Handle Generate Request
  const handleGenerate = async () => {
    if (!prompt.trim()) return

    setIsGenerating(true)
    setErrorMessage(null)
    setStatusMessage('Generating 3D model via Blender...')

    try {
      const res = await fetch('/api/plugins/blender/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: prompt.trim(),
          format: outputFormat,
          preset,
          quality
        })
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => ({ detail: 'Generation failed' }))
        throw new Error(errData.detail?.message || errData.detail || 'Blender execution error')
      }

      const result = await res.json()
      setStatusMessage(`Complete in ${result.duration_seconds}s`)

      if (result.format === 'glb' || result.format === 'gltf') {
        setModelUrl(result.url)
        setCurrentModelName(result.filename)
        setRenderedImageUrl(null)
      } else {
        setRenderedImageUrl(result.url)
      }

      void fetchStatusAndModels()
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to generate 3D model')
      setStatusMessage(null)
    } finally {
      setIsGenerating(false)
    }
  }

  // Handle local file drop or upload
  const handleFileUpload = (file: File) => {
    const ext = file.name.split('.').pop()?.toLowerCase()
    if (!ext || !['glb', 'gltf', 'obj'].includes(ext)) {
      setErrorMessage('Please provide a .glb, .gltf, or .obj 3D model file')
      return
    }

    const objectUrl = URL.createObjectURL(file)
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

  // Snapshot download
  const handleTakeSnapshot = () => {
    if (!viewportRef.current) return
    const dataUrl = viewportRef.current.takeSnapshot()
    if (!dataUrl) return

    const link = document.createElement('a')
    link.download = `${currentModelName}_snapshot.png`
    link.href = dataUrl
    link.click()
  }

  return (
    <div className="flex h-full w-full flex-col bg-(--ui-background) text-(--ui-text-primary) overflow-hidden font-sans select-none">
      {/* --- TOP TOOLBAR --- */}
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-(--ui-border) px-4 bg-(--ui-panel-background)/60 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="flex size-7 items-center justify-center rounded-lg bg-violet-600/20 text-violet-400 border border-violet-500/30">
              <Box className="size-4" />
            </span>
            <span className="text-sm font-semibold tracking-wide">Blender 3D Studio</span>
          </div>

          <div className="h-4 w-px bg-(--ui-border) mx-1" />

          {/* Model info pill */}
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-(--ui-surface-background)/80 border border-(--ui-border)/60 text-xs font-mono text-(--ui-text-secondary)">
            <span className="size-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="truncate max-w-[200px]">{currentModelName}</span>
          </div>
        </div>

        {/* Viewport display modes */}
        <div className="flex items-center gap-1">
          {/* Shading mode */}
          <div className="flex items-center rounded-lg border border-(--ui-border) bg-(--ui-surface-background) p-0.5 text-xs">
            {(['textured', 'wireframe', 'normal', 'matcap'] as ShadingMode[]).map(mode => (
              <button
                key={mode}
                onClick={() => setShadingMode(mode)}
                className={cn(
                  'px-2 py-1 rounded capitalize transition-all cursor-pointer',
                  shadingMode === mode
                    ? 'bg-violet-600 text-white font-medium shadow-xs'
                    : 'text-(--ui-text-tertiary) hover:text-(--ui-text-primary)'
                )}
              >
                {mode}
              </button>
            ))}
          </div>

          <div className="h-4 w-px bg-(--ui-border) mx-1" />

          {/* Camera Angles */}
          <div className="flex items-center rounded-lg border border-(--ui-border) bg-(--ui-surface-background) p-0.5 text-xs">
            {(['iso', 'front', 'top', 'side'] as CameraAngle[]).map(angle => (
              <button
                key={angle}
                onClick={() => viewportRef.current?.resetCamera(angle)}
                className="px-2 py-1 rounded uppercase font-mono text-[0.65rem] text-(--ui-text-tertiary) hover:text-(--ui-text-primary) hover:bg-(--ui-hover) cursor-pointer"
                title={`Align camera to ${angle} view`}
              >
                {angle}
              </button>
            ))}
          </div>

          <div className="h-4 w-px bg-(--ui-border) mx-1" />

          {/* Toggles: Grid, Axes, Auto-Rotate */}
          <button
            onClick={() => setShowGrid(!showGrid)}
            className={cn(
              'flex items-center gap-1 px-2 py-1 rounded-md border text-xs cursor-pointer transition-colors',
              showGrid
                ? 'border-violet-500/40 bg-violet-500/10 text-violet-300'
                : 'border-(--ui-border) text-(--ui-text-tertiary) hover:text-(--ui-text-primary)'
            )}
            title="Toggle Ground Grid"
          >
            <Layers3 className="size-3.5" />
            <span>Grid</span>
          </button>

          <button
            onClick={() => setAutoRotate(!autoRotate)}
            className={cn(
              'flex items-center gap-1 px-2 py-1 rounded-md border text-xs cursor-pointer transition-colors',
              autoRotate
                ? 'border-violet-500/40 bg-violet-500/10 text-violet-300'
                : 'border-(--ui-border) text-(--ui-text-tertiary) hover:text-(--ui-text-primary)'
            )}
            title="Auto Rotate Turntable"
          >
            <RefreshCw className={cn('size-3.5', autoRotate && 'animate-spin')} />
            <span>Orbit</span>
          </button>

          {/* Snapshot Button */}
          <button
            onClick={handleTakeSnapshot}
            className="flex items-center gap-1 px-2.5 py-1 rounded-md border border-(--ui-border) bg-(--ui-surface-background) text-xs hover:bg-(--ui-hover) cursor-pointer"
            title="Take Viewport Snapshot (PNG)"
          >
            <Eye className="size-3.5 text-violet-400" />
            <span>Capture</span>
          </button>

          {/* Upload Button */}
          <input
            type="file"
            ref={fileInputRef}
            onChange={e => {
              if (e.target.files && e.target.files[0]) {
                handleFileUpload(e.target.files[0])
              }
            }}
            accept=".glb,.gltf,.obj"
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-1 px-2.5 py-1 rounded-md border border-(--ui-border) bg-(--ui-surface-background) text-xs hover:bg-(--ui-hover) cursor-pointer"
            title="Open 3D File (.glb, .gltf, .obj)"
          >
            <Upload className="size-3.5" />
            <span>Open</span>
          </button>
        </div>
      </header>

      {/* --- MAIN WORKSPACE AREA --- */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* VIEWPORT AREA */}
        <div
          className={cn(
            'relative flex-1 h-full min-w-0 bg-[#0c0d12] transition-all',
            isDragOver && 'ring-2 ring-violet-500 ring-inset bg-violet-950/20'
          )}
          onDragOver={e => {
            e.preventDefault()
            setIsDragOver(true)
          }}
          onDragLeave={() => setIsDragOver(false)}
          onDrop={handleDrop}
        >
          {/* If render mode result is PNG, show image preview overlay */}
          {renderedImageUrl ? (
            <div className="absolute inset-0 flex flex-col items-center justify-center p-6 bg-black/80 z-10 backdrop-blur-xs">
              <img
                src={renderedImageUrl}
                alt="Render Result"
                className="max-h-[80%] max-w-[90%] rounded-xl object-contain shadow-2xl border border-white/10"
              />
              <div className="mt-4 flex items-center gap-3">
                <a
                  href={renderedImageUrl}
                  download="blender_render.png"
                  className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 text-white text-xs font-medium shadow-lg transition-all"
                >
                  <Download className="size-4" />
                  <span>Download Render</span>
                </a>
                <button
                  onClick={() => setRenderedImageUrl(null)}
                  className="px-4 py-2 rounded-lg border border-(--ui-border) bg-(--ui-surface-background) hover:bg-(--ui-hover) text-xs"
                >
                  Back to 3D Viewport
                </button>
              </div>
            </div>
          ) : null}

          {/* 3D WebGL Canvas Viewport */}
          <BlenderViewport
            ref={viewportRef}
            modelUrl={modelUrl}
            shadingMode={shadingMode}
            showGrid={showGrid}
            showAxes={showAxes}
            autoRotate={autoRotate}
            lightIntensity={lightIntensity}
            onStatsChange={setStats}
            onError={err => setErrorMessage(err)}
          />

          {/* Model Mesh Statistics HUD (Bottom Left) */}
          <div className="absolute bottom-4 left-4 flex items-center gap-3 rounded-lg border border-white/10 bg-black/60 px-3 py-1.5 backdrop-blur-md text-[0.7rem] font-mono text-zinc-400">
            <div>
              <span className="text-zinc-500">Verts: </span>
              <span className="text-violet-400 font-semibold">{stats.vertices.toLocaleString()}</span>
            </div>
            <div className="h-3 w-px bg-white/10" />
            <div>
              <span className="text-zinc-500">Tris: </span>
              <span className="text-violet-400 font-semibold">{stats.triangles.toLocaleString()}</span>
            </div>
            <div className="h-3 w-px bg-white/10" />
            <div>
              <span className="text-zinc-500">Meshes: </span>
              <span className="text-zinc-200">{stats.meshes}</span>
            </div>
          </div>

          {/* Navigation Controls Tooltip HUD (Bottom Right) */}
          <div className="absolute bottom-4 right-4 flex items-center gap-2 rounded-lg border border-white/10 bg-black/60 px-3 py-1.5 backdrop-blur-md text-[0.68rem] text-zinc-400">
            <span>🖱️ Rotate: <b className="text-zinc-200">Left-Drag</b></span>
            <span>• Pan: <b className="text-zinc-200">Right-Drag</b></span>
            <span>• Zoom: <b className="text-zinc-200">Wheel</b></span>
          </div>

          {/* Drag & Drop Visual Hint */}
          {isDragOver && (
            <div className="absolute inset-0 flex items-center justify-center bg-violet-950/40 backdrop-blur-xs z-30 pointer-events-none">
              <div className="flex flex-col items-center gap-2 rounded-2xl border-2 border-dashed border-violet-400 bg-black/70 p-8 shadow-2xl">
                <Box className="size-12 text-violet-400 animate-bounce" />
                <span className="text-base font-semibold text-white">Drop 3D Model to Inspect</span>
                <span className="text-xs text-zinc-400">Supports .glb, .gltf, .obj</span>
              </div>
            </div>
          )}
        </div>

        {/* --- RIGHT SIDEBAR: GENERATOR & LIBRARY --- */}
        <aside className="w-80 shrink-0 border-l border-(--ui-border) bg-(--ui-panel-background)/40 flex flex-col overflow-hidden">
          {/* Tab Selector */}
          <div className="flex border-b border-(--ui-border)">
            <button
              onClick={() => setActiveTab('generate')}
              className={cn(
                'flex-1 py-2.5 text-xs font-medium text-center border-b-2 transition-colors cursor-pointer',
                activeTab === 'generate'
                  ? 'border-violet-500 text-violet-400 bg-violet-500/5 font-semibold'
                  : 'border-transparent text-(--ui-text-secondary) hover:text-(--ui-text-primary)'
              )}
            >
              Generate 3D
            </button>
            <button
              onClick={() => setActiveTab('library')}
              className={cn(
                'flex-1 py-2.5 text-xs font-medium text-center border-b-2 transition-colors cursor-pointer',
                activeTab === 'library'
                  ? 'border-violet-500 text-violet-400 bg-violet-500/5 font-semibold'
                  : 'border-transparent text-(--ui-text-secondary) hover:text-(--ui-text-primary)'
              )}
            >
              Models Library ({modelsList.length})
            </button>
          </div>

          {/* TAB 1: GENERATE STUDIO */}
          {activeTab === 'generate' && (
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {/* Natural language prompt */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-(--ui-text-secondary) flex items-center justify-between">
                  <span>Prompt Description</span>
                  <span className="text-[0.68rem] text-violet-400">Blender bpy</span>
                </label>
                <textarea
                  value={prompt}
                  onChange={e => setPrompt(e.target.value)}
                  placeholder="Describe the 3D model, prop, or architecture to create..."
                  className="w-full h-24 rounded-lg border border-(--ui-border) bg-(--ui-surface-background) p-2.5 text-xs text-(--ui-text-primary) placeholder:text-(--ui-text-quaternary) focus:border-violet-500 focus:outline-hidden resize-none leading-relaxed"
                />
              </div>

              {/* Archetype / Style Presets */}
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
                      key={item.id}
                      onClick={() => setPreset(item.id)}
                      className={cn(
                        'flex items-center justify-center px-2 py-1.5 rounded-md border text-xs transition-all cursor-pointer',
                        preset === item.id
                          ? 'border-violet-500 bg-violet-500/15 text-violet-300 font-medium'
                          : 'border-(--ui-border) bg-(--ui-surface-background)/50 text-(--ui-text-secondary) hover:bg-(--ui-hover)'
                      )}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Format & Quality Settings */}
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <label className="text-[0.7rem] font-semibold text-(--ui-text-secondary)">Output Format</label>
                  <select
                    value={outputFormat}
                    onChange={e => setOutputFormat(e.target.value as OutputFormat)}
                    className="w-full rounded-md border border-(--ui-border) bg-(--ui-surface-background) px-2 py-1.5 text-xs focus:outline-hidden"
                  >
                    <option value="glb">GLB (3D Model)</option>
                    <option value="png">PNG (Render)</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <label className="text-[0.7rem] font-semibold text-(--ui-text-secondary)">Engine Quality</label>
                  <select
                    value={quality}
                    onChange={e => setQuality(e.target.value as RenderQuality)}
                    className="w-full rounded-md border border-(--ui-border) bg-(--ui-surface-background) px-2 py-1.5 text-xs focus:outline-hidden"
                  >
                    <option value="draft">Draft (EEVEE)</option>
                    <option value="final">Final (Cycles)</option>
                  </select>
                </div>
              </div>

              {/* Lighting Slider */}
              <div className="space-y-1 pt-1">
                <div className="flex justify-between text-[0.7rem] text-(--ui-text-secondary)">
                  <span className="flex items-center gap-1">
                    <Sun className="size-3 text-amber-400" />
                    <span>Studio Lighting</span>
                  </span>
                  <span>{Math.round(lightIntensity * 100)}%</span>
                </div>
                <input
                  type="range"
                  min="0.2"
                  max="2.5"
                  step="0.1"
                  value={lightIntensity}
                  onChange={e => setLightIntensity(parseFloat(e.target.value))}
                  className="w-full accent-violet-500 cursor-pointer"
                />
              </div>

              {/* Generate Button */}
              <button
                onClick={handleGenerate}
                disabled={isGenerating || !prompt.trim()}
                className={cn(
                  'w-full py-2.5 rounded-lg flex items-center justify-center gap-2 text-xs font-semibold text-white shadow-lg transition-all cursor-pointer',
                  isGenerating
                    ? 'bg-violet-700/60 cursor-not-allowed'
                    : 'bg-violet-600 hover:bg-violet-500 active:scale-[0.98]'
                )}
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

              {/* Status / Error feedback */}
              {statusMessage && (
                <div className="flex items-center gap-2 p-2 rounded-md bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs">
                  <Check className="size-3.5 shrink-0" />
                  <span>{statusMessage}</span>
                </div>
              )}

              {errorMessage && (
                <div className="flex items-start gap-2 p-2 rounded-md bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">
                  <AlertCircle className="size-3.5 shrink-0 mt-0.5" />
                  <span className="break-words">{errorMessage}</span>
                </div>
              )}

              {/* Blender Engine Diagnostics Box */}
              <div className="mt-4 rounded-lg border border-(--ui-border) bg-(--ui-surface-background)/40 p-3 text-xs space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[0.7rem] uppercase tracking-wider text-(--ui-text-tertiary) font-semibold">
                    Blender Environment
                  </span>
                  <span
                    className={cn(
                      'size-2 rounded-full',
                      blenderStatus.available ? 'bg-emerald-500' : 'bg-amber-500'
                    )}
                  />
                </div>
                <div className="text-[0.75rem] text-(--ui-text-secondary) font-mono">
                  {blenderStatus.version}
                </div>
                {blenderStatus.path && (
                  <div className="text-[0.65rem] text-(--ui-text-quaternary) truncate font-mono" title={blenderStatus.path}>
                    {blenderStatus.path}
                  </div>
                )}
                {!blenderStatus.available && (
                  <p className="text-[0.7rem] text-amber-400/90 leading-relaxed">
                    Install Blender from <a href="https://www.blender.org/download/" target="_blank" rel="noreferrer" className="underline font-semibold">blender.org</a> to generate new models. Previews of local models are always interactive!
                  </p>
                )}
              </div>
            </div>
          )}

          {/* TAB 2: MODELS LIBRARY */}
          {activeTab === 'library' && (
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              <div className="flex items-center justify-between px-1 text-xs text-(--ui-text-secondary)">
                <span>Recent Assets</span>
                <button
                  onClick={fetchStatusAndModels}
                  className="hover:text-(--ui-text-primary) p-1 rounded cursor-pointer"
                  title="Refresh library"
                >
                  <RefreshCw className="size-3" />
                </button>
              </div>

              {modelsList.length === 0 ? (
                <div className="flex flex-col items-center justify-center p-8 text-center text-xs text-(--ui-text-tertiary)">
                  <Box className="size-8 text-zinc-600 mb-2" />
                  <span>No models generated yet</span>
                  <span className="text-[0.7rem] text-zinc-500 mt-1">Generate your first model above!</span>
                </div>
              ) : (
                modelsList.map(item => (
                  <div
                    key={item.filename}
                    onClick={() => {
                      if (item.format === 'glb' || item.format === 'gltf') {
                        setModelUrl(item.url)
                        setCurrentModelName(item.filename)
                        setRenderedImageUrl(null)
                      } else {
                        setRenderedImageUrl(item.url)
                      }
                    }}
                    className={cn(
                      'flex items-center justify-between p-2.5 rounded-lg border border-(--ui-border) bg-(--ui-surface-background)/60 hover:bg-(--ui-hover) cursor-pointer transition-all',
                      currentModelName === item.filename && 'border-violet-500/80 bg-violet-500/10'
                    )}
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <span className="flex size-7 shrink-0 items-center justify-center rounded bg-violet-500/10 text-violet-400">
                        <Box className="size-3.5" />
                      </span>
                      <div className="min-w-0">
                        <div className="truncate text-xs font-medium text-(--ui-text-primary)">
                          {item.filename}
                        </div>
                        <div className="text-[0.68rem] text-(--ui-text-tertiary) font-mono">
                          {(item.size_bytes / 1024).toFixed(1)} KB • {item.format.toUpperCase()}
                        </div>
                      </div>
                    </div>
                    <a
                      href={item.url}
                      download={item.filename}
                      onClick={e => e.stopPropagation()}
                      className="p-1 text-(--ui-text-tertiary) hover:text-(--ui-text-primary)"
                      title="Download file"
                    >
                      <Download className="size-3.5" />
                    </a>
                  </div>
                ))
              )}
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}
