'use client'

import { type FC, useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js'

import { requestComposerInsert } from '@/app/chat/composer/focus'
import { useComposerScope } from '@/app/chat/composer/scope'
import { useSessionView } from '@/app/chat/session-view'
import { navigateWorkspaceHash } from '@/app/routes'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/ui/error-state'
import { Loader } from '@/components/ui/loader'
import { Tip } from '@/components/ui/tooltip'
import { useI18n } from '@/i18n'
import {
  blenderModelFromResult,
  type BlenderModelResultData,
  detectModelFormat,
  studioDeepLinkHash
} from '@/lib/generated-models'
import { Box, Download, ExternalLink, Eye, Layers3, RefreshCw, Zap } from '@/lib/icons'
import { cn } from '@/lib/utils'
import { recordSessionModel } from '@/store/blender-models'

interface GeneratedModelProps {
  args?: Record<string, unknown>
  modelUrl?: string
  result?: unknown
  title?: string
}

function extractResultErrorMessage(result: unknown): string | null {
  if (!result) {
    return null
  }

  if (typeof result === 'string') {
    const trimmed = result.trim()

    if (!trimmed) {
      return null
    }

    try {
      const parsed = JSON.parse(trimmed) as Record<string, unknown>

      if (typeof parsed.error === 'string' && parsed.error.trim()) {
        return parsed.error.trim()
      }

      if (typeof parsed.message === 'string' && parsed.success === false) {
        return parsed.message.trim()
      }
    } catch {
      return trimmed.slice(0, 240)
    }
  }

  if (typeof result === 'object') {
    const row = result as Record<string, unknown>

    if (typeof row.error === 'string' && row.error.trim()) {
      return row.error.trim()
    }

    if (typeof row.message === 'string' && row.success === false) {
      return row.message.trim()
    }
  }

  return null
}

export const GeneratedModelResult: FC<GeneratedModelProps> = ({ args, modelUrl, result, title }) => {
  const { t } = useI18n()
  const b3d = t.blender3d
  const scope = useComposerScope()
  const sessionView = useSessionView()
  const containerRef = useRef<HTMLDivElement>(null)

  const engineRef = useRef<{
    animId: null | number
    camera: any
    controls: any
    modelGroup: any
    renderer: any
    scene: any
  }>({
    animId: null,
    camera: null,
    controls: null,
    modelGroup: null,
    renderer: null,
    scene: null
  })

  const isPending = result === undefined && !modelUrl
  const modelData: BlenderModelResultData | null = result !== undefined ? blenderModelFromResult(result) : null

  const resolvedUrl = modelUrl || modelData?.displayUrl || ''
  const resolvedFormat = modelData?.format || detectModelFormat(resolvedUrl || title)
  const displayTitle = title || modelData?.prompt || (typeof args?.prompt === 'string' ? args.prompt : '3D Model')
  const isImageStill = resolvedFormat === 'png'

  const [wireframe, setWireframe] = useState(false)
  const [autoRotate, setAutoRotate] = useState(true)
  const [zoomActive, setZoomActive] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [reloadNonce, setReloadNonce] = useState(0)
  const [stats, setStats] = useState({ tris: 0, verts: 0 })

  // Record completed tool-generated models into the session's 3D context store post-render
  useEffect(() => {
    if (!modelData) {
      return
    }

    const sessionId = sessionView.$runtimeId.get() || '__draft__'

    recordSessionModel(sessionId, {
      durationSeconds: modelData.duration_seconds,
      filename: modelData.filename,
      format: modelData.format,
      localPath: modelData.output_path,
      name: modelData.prompt ? modelData.prompt.slice(0, 35) : modelData.filename,
      prompt: modelData.prompt,
      sessionId,
      sizeBytes: modelData.file_size_bytes,
      url: modelData.displayUrl
    })
  }, [modelData, sessionView])

  useEffect(() => {
    if (isPending || isImageStill || !resolvedUrl) {
      return
    }

    const container = containerRef.current

    if (!container) {
      return
    }

    const engine = engineRef.current
    const width = container.clientWidth || 480
    const height = 240

    const scene = new THREE.Scene()
    engine.scene = scene

    const camera = new THREE.PerspectiveCamera(40, width / height, 0.1, 50)
    camera.position.set(2.8, 2.2, 2.8)
    engine.camera = camera

    const renderer = new THREE.WebGLRenderer({
      alpha: true,
      antialias: true,
      powerPreference: 'default',
      preserveDrawingBuffer: true
    })

    renderer.setSize(width, height)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    container.appendChild(renderer.domElement)
    engine.renderer = renderer

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.05
    controls.maxDistance = 15
    controls.minDistance = 0.8
    controls.autoRotate = true
    controls.autoRotateSpeed = 2.0
    // Keep wheel zoom off until clicked or ⌘/Ctrl-held so normal transcript scrolling never traps on the canvas.
    controls.enableZoom = false
    engine.controls = controls

    const onWheelCapture = (event: WheelEvent) => {
      if (event.metaKey || event.ctrlKey) {
        controls.enableZoom = true
      }
    }

    renderer.domElement.addEventListener('wheel', onWheelCapture, { capture: true, passive: true })

    const ambient = new THREE.AmbientLight(0xffffff, 0.7)
    scene.add(ambient)

    const keyLight = new THREE.DirectionalLight(0xfff5e6, 1.2)
    keyLight.position.set(4, 6, 4)
    scene.add(keyLight)

    const fillLight = new THREE.DirectionalLight(0xddeeff, 0.5)
    fillLight.position.set(-5, 2, -3)
    scene.add(fillLight)

    const grid = new THREE.GridHelper(6, 12, 0x444455, 0x222233)
    grid.position.y = -0.01
    scene.add(grid)

    let cancelled = false
    setLoading(true)
    setLoadError(null)

    const mountModel = (model: any) => {
      if (cancelled) {
        return
      }

      engine.modelGroup = model

      let verts = 0
      let tris = 0

      model.traverse((child: any) => {
        if (!child.isMesh) {
          return
        }

        if (!child.material) {
          child.material = new THREE.MeshStandardMaterial({
            color: 0xd4d4d8,
            metalness: 0.25,
            roughness: 0.45
          })
        }

        child.userData.origMat = child.material
        const geom = child.geometry

        if (geom) {
          if (geom.attributes.position) {
            verts += geom.attributes.position.count
          }

          if (geom.index) {
            tris += geom.index.count / 3
          } else if (geom.attributes.position) {
            tris += geom.attributes.position.count / 3
          }
        }
      })

      const box = new THREE.Box3().setFromObject(model)
      const size = box.getSize(new THREE.Vector3())
      const center = box.getCenter(new THREE.Vector3())

      const maxDim = Math.max(size.x, size.y, size.z) || 1
      const scale = 2.0 / maxDim
      model.scale.setScalar(scale)

      model.position.x = -center.x * scale
      model.position.y = -box.min.y * scale
      model.position.z = -center.z * scale

      scene.add(model)
      setStats({ tris: Math.round(tris), verts: Math.round(verts) })
      setLoading(false)

      controls.target.set(0, 0.5, 0)
      camera.position.set(2.8, 2.0, 2.8)
      camera.lookAt(0, 0.5, 0)
      controls.update()
      renderer.render(scene, camera)
    }

    const handleLoadError = (err: any) => {
      if (cancelled) {
        return
      }

      console.error('Failed to load in-chat 3D model:', err)
      setLoading(false)
      setLoadError(err instanceof Error ? err.message : b3d.loadFailed)
    }

    if (resolvedFormat === 'obj') {
      const objLoader = new OBJLoader()
      objLoader.load(resolvedUrl, mountModel, undefined, handleLoadError)
    } else {
      const gltfLoader = new GLTFLoader()
      gltfLoader.load(resolvedUrl, (gltf: any) => mountModel(gltf.scene || gltf.scenes[0]), undefined, handleLoadError)
    }

    let disposed = false
    let inViewport = true
    let pageVisible = typeof document === 'undefined' ? true : document.visibilityState === 'visible'

    const scheduleOrPause = () => {
      const shouldRun = !disposed && inViewport && pageVisible

      if (shouldRun && engine.animId === null) {
        const animate = () => {
          if (disposed || !inViewport || !pageVisible) {
            engine.animId = null

            return
          }

          engine.animId = requestAnimationFrame(animate)

          if (engine.controls) {
            engine.controls.update()
          }

          renderer.render(scene, camera)
        }

        engine.animId = requestAnimationFrame(animate)
      } else if (!shouldRun && engine.animId !== null) {
        cancelAnimationFrame(engine.animId)
        engine.animId = null
      }
    }

    scheduleOrPause()

    const intersectionObserver =
      typeof IntersectionObserver !== 'undefined'
        ? new IntersectionObserver(
            entries => {
              inViewport = entries.some(entry => entry.isIntersecting)
              scheduleOrPause()
            },
            { threshold: 0.05 }
          )
        : null

    intersectionObserver?.observe(container)

    const onVisibilityChange = () => {
      pageVisible = document.visibilityState === 'visible'
      scheduleOrPause()
    }

    document.addEventListener('visibilitychange', onVisibilityChange)

    const resizeObserver = new ResizeObserver(() => {
      if (!container || !engine.renderer || !engine.camera) {
        return
      }

      const w = container.clientWidth

      if (w === 0) {
        return
      }

      engine.camera.aspect = w / height
      engine.camera.updateProjectionMatrix()
      engine.renderer.setSize(w, height)
    })

    resizeObserver.observe(container)

    return () => {
      cancelled = true
      disposed = true

      if (engine.animId !== null) {
        cancelAnimationFrame(engine.animId)
        engine.animId = null
      }

      renderer.domElement.removeEventListener('wheel', onWheelCapture, { capture: true })
      document.removeEventListener('visibilitychange', onVisibilityChange)
      intersectionObserver?.disconnect()
      resizeObserver.disconnect()
      controls.dispose()
      renderer.dispose()

      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement)
      }
    }
  }, [b3d.loadFailed, isImageStill, isPending, reloadNonce, resolvedFormat, resolvedUrl])

  useEffect(() => {
    if (engineRef.current.controls) {
      engineRef.current.controls.enableZoom = zoomActive
    }

    if (!zoomActive) {
      return
    }

    const onPointerDownOutside = (event: PointerEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setZoomActive(false)
      }
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setZoomActive(false)
      }
    }

    const onKeyUp = (event: KeyboardEvent) => {
      if (!event.metaKey && !event.ctrlKey && engineRef.current.controls && !zoomActive) {
        engineRef.current.controls.enableZoom = false
      }
    }

    window.addEventListener('pointerdown', onPointerDownOutside)
    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('keyup', onKeyUp)

    return () => {
      window.removeEventListener('pointerdown', onPointerDownOutside)
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('keyup', onKeyUp)
    }
  }, [zoomActive])

  useEffect(() => {
    if (!engineRef.current.modelGroup) {
      return
    }

    engineRef.current.modelGroup.traverse((child: any) => {
      if (!child.isMesh) {
        return
      }

      if (wireframe) {
        child.material = new THREE.MeshBasicMaterial({ color: 0x00ffcc, wireframe: true })
      } else if (child.userData.origMat) {
        child.material = child.userData.origMat
      }
    })
  }, [wireframe])

  useEffect(() => {
    if (engineRef.current.controls) {
      engineRef.current.controls.autoRotate = autoRotate
    }
  }, [autoRotate])

  const handleSnapshot = () => {
    const { camera, renderer, scene } = engineRef.current

    if (!renderer || !scene || !camera) {
      return
    }

    renderer.render(scene, camera)
    const dataUrl = renderer.domElement.toDataURL('image/png')
    const link = document.createElement('a')
    link.download = `${modelData?.filename || 'model'}_preview.png`
    link.href = dataUrl
    link.click()
  }

  const handleRefineInChat = () => {
    requestComposerInsert(`Refine 3D model (${displayTitle}): `, { target: scope.target })
  }

  const handleOpenStudio = () => {
    navigateWorkspaceHash(
      studioDeepLinkHash({
        format: resolvedFormat,
        localPath: modelData?.output_path,
        name: modelData?.filename || displayTitle,
        url: resolvedUrl
      })
    )
  }

  if (isPending) {
    return (
      <div className="my-2.5 max-w-xl rounded-xl border border-(--ui-stroke-tertiary) bg-(--ui-bg-elevated) p-4 shadow-xs">
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="flex size-6 items-center justify-center rounded-md bg-primary/12 text-primary">
              <Box className="size-3.5" />
            </span>
            <span className="text-xs font-semibold text-(--ui-text-primary)">{b3d.generatorTitle}</span>
          </div>
          <span className="font-mono text-[0.6875rem] text-(--ui-text-tertiary)">{b3d.runningHeadless}</span>
        </div>

        <div className="flex h-44 w-full flex-col items-center justify-center gap-2.5 rounded-lg border border-dashed border-(--ui-stroke-secondary) bg-(--ui-bg-card)">
          <Loader className="size-8" type="lemniscate-bloom" />
          <span className="px-4 text-center text-xs font-medium text-(--ui-text-primary)">
            {typeof args?.prompt === 'string' ? args.prompt : b3d.generatingAsset}
          </span>
          <span className="font-mono text-[0.6875rem] text-(--ui-text-tertiary)">{b3d.buildingGeometry}</span>
        </div>
      </div>
    )
  }

  if (!resolvedUrl) {
    const failureText = extractResultErrorMessage(result) || b3d.generationFailed

    return (
      <div className="my-2.5 max-w-xl rounded-xl border border-(--ui-stroke-tertiary) bg-(--ui-bg-elevated) p-4 shadow-xs">
        <ErrorState description={failureText} title={b3d.generationFailed}>
          <div className="flex justify-center">
            <Button onClick={handleRefineInChat} size="sm" type="button" variant="secondary">
              <Zap className="size-3.5" />
              <span>{b3d.iterateInChat}</span>
            </Button>
          </div>
        </ErrorState>
      </div>
    )
  }

  if (isImageStill) {
    return (
      <div className="my-2.5 max-w-xl overflow-hidden rounded-xl border border-(--ui-stroke-tertiary) bg-(--ui-bg-elevated) shadow-xs">
        <div className="flex items-center justify-between border-b border-(--ui-stroke-tertiary) bg-(--ui-bg-card) px-3 py-2">
          <div className="flex items-center gap-2 truncate">
            <Box className="size-3.5 shrink-0 text-primary" />
            <span className="truncate text-xs font-medium text-(--ui-text-primary)">{displayTitle}</span>
          </div>
          <span className="rounded border border-(--ui-stroke-tertiary) bg-(--ui-bg-elevated) px-2 py-0.5 font-mono text-[0.625rem] text-(--ui-text-secondary)">
            {b3d.pngRender}
          </span>
        </div>
        <div className="flex justify-center bg-[#0a0b10] p-3">
          <img alt={displayTitle} className="max-h-72 rounded-lg object-contain" src={resolvedUrl} />
        </div>
        <div className="flex items-center justify-between border-t border-(--ui-stroke-tertiary) bg-(--ui-bg-card) px-3 py-2 text-xs">
          <Button onClick={handleRefineInChat} size="xs" type="button" variant="ghost">
            <Zap className="size-3.5 text-primary" />
            <span>{b3d.refineInChat}</span>
          </Button>
          <a
            className="inline-flex items-center gap-1 rounded-md bg-primary px-2.5 py-1 font-medium text-primary-foreground transition-colors hover:bg-primary/90"
            download="render.png"
            href={resolvedUrl}
          >
            <Download className="size-3.5" />
            <span>{b3d.downloadPng}</span>
          </a>
        </div>
      </div>
    )
  }

  return (
    <div className="my-2.5 max-w-xl overflow-hidden rounded-xl border border-(--ui-stroke-tertiary) bg-(--ui-bg-elevated) shadow-xs">
      <div className="flex items-center justify-between border-b border-(--ui-stroke-tertiary) bg-(--ui-bg-card) px-3.5 py-2.5">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-primary/12 text-primary">
            <Box className="size-3.5" />
          </span>
          <div className="min-w-0">
            <div className="truncate text-xs font-semibold text-(--ui-text-primary)">{displayTitle}</div>
            {stats.verts > 0 && (
              <div className="flex items-center gap-2 font-mono text-[0.65rem] text-(--ui-text-tertiary)">
                <span>{stats.verts.toLocaleString()} verts</span>
                <span>•</span>
                <span>{stats.tris.toLocaleString()} tris</span>
                {modelData?.duration_seconds && (
                  <>
                    <span>•</span>
                    <span className="text-(--ui-green)">{modelData.duration_seconds}s</span>
                  </>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-1">
          <Tip label={b3d.wireframe}>
            <Button
              aria-label={b3d.wireframe}
              aria-pressed={wireframe}
              className={cn('size-7 p-0', wireframe && 'bg-primary/12 text-primary')}
              onClick={() => setWireframe(!wireframe)}
              size="icon"
              type="button"
              variant="ghost"
            >
              <Layers3 className="size-3.5" />
            </Button>
          </Tip>

          <Tip label={b3d.turntable}>
            <Button
              aria-label={b3d.turntable}
              aria-pressed={autoRotate}
              className={cn('size-7 p-0', autoRotate && 'bg-primary/12 text-primary')}
              onClick={() => setAutoRotate(!autoRotate)}
              size="icon"
              type="button"
              variant="ghost"
            >
              <RefreshCw className={cn('size-3.5', autoRotate && 'animate-spin')} />
            </Button>
          </Tip>

          <Tip label={b3d.snapshot}>
            <Button
              aria-label={b3d.snapshot}
              className="size-7 p-0"
              onClick={handleSnapshot}
              size="icon"
              type="button"
              variant="ghost"
            >
              <Eye className="size-3.5" />
            </Button>
          </Tip>
        </div>
      </div>

      <div
        className={cn(
          'relative h-60 w-full overflow-hidden bg-[#0a0b10] select-none',
          zoomActive && 'ring-1 ring-primary/50 ring-inset'
        )}
        onPointerDown={() => setZoomActive(true)}
        ref={containerRef}
      >
        {loading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/55">
            <div className="flex items-center gap-2 rounded-lg border border-white/10 bg-black/80 px-3 py-1.5 text-xs text-zinc-200">
              <Loader className="size-4" />
              <span>{b3d.loadingAsset}</span>
            </div>
          </div>
        )}

        {loadError && !loading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-(--ui-bg-elevated)/95 p-4">
            <ErrorState description={loadError} title={b3d.loadFailed}>
              <div className="flex justify-center">
                <Button onClick={() => setReloadNonce(n => n + 1)} size="xs" type="button" variant="secondary">
                  {t.common.retry}
                </Button>
              </div>
            </ErrorState>
          </div>
        )}

        {!loadError && (
          <div className="pointer-events-none absolute right-2 bottom-2 rounded bg-black/65 px-2 py-0.5 text-[0.625rem] text-zinc-300 backdrop-blur-xs">
            {zoomActive ? b3d.orbitActiveHint : b3d.orbitHint}
          </div>
        )}
      </div>

      <div className="flex items-center justify-between border-t border-(--ui-stroke-tertiary) bg-(--ui-bg-card) px-3 py-2 text-xs">
        <Tip label={b3d.iterateTip}>
          <Button onClick={handleRefineInChat} size="xs" type="button" variant="ghost">
            <Zap className="size-3.5 text-primary" />
            <span>{b3d.iterateInChat}</span>
          </Button>
        </Tip>

        <div className="flex items-center gap-2">
          {resolvedUrl && (
            <a
              className="inline-flex items-center gap-1 rounded-md border border-(--ui-stroke-tertiary) bg-(--ui-bg-elevated) px-2.5 py-1 text-xs text-(--ui-text-primary) transition-colors hover:bg-(--ui-control-hover-background)"
              download={modelData?.filename || `model.${resolvedFormat}`}
              href={resolvedUrl}
            >
              <Download className="size-3" />
              <span>{b3d.downloadFormat(resolvedFormat.toUpperCase())}</span>
            </a>
          )}

          <Tip label={b3d.openStudioTip}>
            <Button onClick={handleOpenStudio} size="xs" type="button">
              <span>{b3d.openStudio}</span>
              <ExternalLink className="size-3" />
            </Button>
          </Tip>
        </div>
      </div>
    </div>
  )
}
