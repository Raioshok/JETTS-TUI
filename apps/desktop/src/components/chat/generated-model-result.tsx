'use client'

import { type FC, useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js'

import { requestComposerInsert } from '@/app/chat/composer/focus'
import { useSessionView } from '@/app/chat/session-view'
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

export const GeneratedModelResult: FC<GeneratedModelProps> = ({ args, modelUrl, result, title }) => {
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
  const [loading, setLoading] = useState(true)
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
      powerPreference: 'high-performance',
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
    engine.controls = controls

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
    }

    const handleLoadError = (err: any) => {
      if (cancelled) {
        return
      }

      console.error('Failed to load in-chat 3D model:', err)
      setLoading(false)
    }

    if (resolvedFormat === 'obj') {
      const objLoader = new OBJLoader()
      objLoader.load(resolvedUrl, mountModel, undefined, handleLoadError)
    } else {
      const gltfLoader = new GLTFLoader()
      gltfLoader.load(
        resolvedUrl,
        (gltf: any) => mountModel(gltf.scene || gltf.scenes[0]),
        undefined,
        handleLoadError
      )
    }

    let running = true

    const animate = () => {
      if (!running) {
        return
      }

      engine.animId = requestAnimationFrame(animate)

      if (engine.controls) {
        engine.controls.update()
      }

      renderer.render(scene, camera)
    }

    animate()

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
      running = false

      if (engine.animId) {
        cancelAnimationFrame(engine.animId)
      }

      resizeObserver.disconnect()
      controls.dispose()
      renderer.dispose()

      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement)
      }
    }
  }, [isImageStill, isPending, resolvedFormat, resolvedUrl])

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
    requestComposerInsert(`Refine 3D model (${displayTitle}): `)
  }

  const handleOpenStudio = () => {
    window.location.hash = studioDeepLinkHash({
      format: resolvedFormat,
      localPath: modelData?.output_path,
      name: modelData?.filename || displayTitle,
      url: resolvedUrl
    })
  }

  if (isPending) {
    return (
      <div className="my-2.5 max-w-xl rounded-xl border border-violet-500/30 bg-(--ui-surface-background)/90 p-4 shadow-xl backdrop-blur-md">
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="flex size-6 items-center justify-center rounded-md border border-violet-500/30 bg-violet-600/20 text-violet-400">
              <Box className="size-3.5 animate-pulse" />
            </span>
            <span className="text-xs font-semibold text-(--ui-text-primary)">Blender 3D Generator</span>
          </div>
          <span className="animate-pulse font-mono text-[0.68rem] text-violet-400">Running headless bpy...</span>
        </div>

        <div className="flex h-44 w-full flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-violet-500/30 bg-black/40">
          <div className="relative flex size-12 items-center justify-center">
            <div className="absolute inset-0 animate-ping rounded-full border-2 border-violet-500/20" />
            <div className="size-8 animate-spin rounded-lg border border-violet-400 bg-violet-500/20" />
          </div>
          <span className="text-xs font-medium text-zinc-300">
            {typeof args?.prompt === 'string' ? args.prompt : 'Generating 3D asset...'}
          </span>
          <span className="font-mono text-[0.68rem] text-zinc-500">Building geometry, shaders & lighting</span>
        </div>
      </div>
    )
  }

  if (isImageStill && resolvedUrl) {
    return (
      <div className="my-2.5 max-w-xl overflow-hidden rounded-xl border border-(--ui-border) bg-(--ui-surface-background)/90 shadow-xl">
        <div className="flex items-center justify-between border-b border-(--ui-border) bg-(--ui-panel-background)/50 px-3 py-2">
          <div className="flex items-center gap-2 truncate">
            <Box className="size-3.5 shrink-0 text-violet-400" />
            <span className="truncate text-xs font-medium">{displayTitle}</span>
          </div>
          <span className="rounded border border-violet-500/20 bg-violet-500/10 px-2 py-0.5 font-mono text-[0.65rem] text-violet-300">
            PNG Render
          </span>
        </div>
        <div className="flex justify-center bg-black/40 p-3">
          <img alt={displayTitle} className="max-h-72 rounded-lg object-contain" src={resolvedUrl} />
        </div>
        <div className="flex items-center justify-between border-t border-(--ui-border) bg-(--ui-panel-background)/40 px-3 py-2 text-xs">
          <button
            className="flex cursor-pointer items-center gap-1 text-violet-400 hover:text-violet-300"
            onClick={handleRefineInChat}
            type="button"
          >
            <Zap className="size-3.5" />
            <span>Refine in Chat</span>
          </button>
          <a
            className="flex items-center gap-1 rounded bg-violet-600 px-2.5 py-1 font-medium text-white hover:bg-violet-500"
            download="render.png"
            href={resolvedUrl}
          >
            <Download className="size-3.5" />
            <span>Download PNG</span>
          </a>
        </div>
      </div>
    )
  }

  return (
    <div className="my-2.5 max-w-xl overflow-hidden rounded-xl border border-(--ui-border) bg-(--ui-surface-background)/95 shadow-2xl backdrop-blur-md">
      <div className="flex items-center justify-between border-b border-(--ui-border) bg-(--ui-panel-background)/60 px-3.5 py-2.5">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="flex size-6 shrink-0 items-center justify-center rounded-md border border-violet-500/30 bg-violet-600/20 text-violet-400">
            <Box className="size-3.5" />
          </span>
          <div className="min-w-0">
            <div className="truncate text-xs font-semibold text-(--ui-text-primary)">{displayTitle}</div>
            {stats.verts > 0 && (
              <div className="flex items-center gap-2 font-mono text-[0.65rem] text-zinc-400">
                <span>{stats.verts.toLocaleString()} verts</span>
                <span>•</span>
                <span>{stats.tris.toLocaleString()} tris</span>
                {modelData?.duration_seconds && (
                  <>
                    <span>•</span>
                    <span className="text-emerald-400">{modelData.duration_seconds}s</span>
                  </>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-1">
          <button
            className={cn(
              'cursor-pointer rounded-md border p-1.5 text-xs transition-colors',
              wireframe
                ? 'border-violet-500/50 bg-violet-500/15 text-violet-300'
                : 'border-(--ui-border) text-(--ui-text-tertiary) hover:text-(--ui-text-primary)'
            )}
            onClick={() => setWireframe(!wireframe)}
            title="Toggle Wireframe"
            type="button"
          >
            <Layers3 className="size-3.5" />
          </button>

          <button
            className={cn(
              'cursor-pointer rounded-md border p-1.5 text-xs transition-colors',
              autoRotate
                ? 'border-violet-500/50 bg-violet-500/15 text-violet-300'
                : 'border-(--ui-border) text-(--ui-text-tertiary) hover:text-(--ui-text-primary)'
            )}
            onClick={() => setAutoRotate(!autoRotate)}
            title="Toggle Turntable Rotation"
            type="button"
          >
            <RefreshCw className={cn('size-3.5', autoRotate && 'animate-spin')} />
          </button>

          <button
            className="cursor-pointer rounded-md border border-(--ui-border) p-1.5 text-(--ui-text-tertiary) hover:text-(--ui-text-primary)"
            onClick={handleSnapshot}
            title="Take Snapshot"
            type="button"
          >
            <Eye className="size-3.5" />
          </button>
        </div>
      </div>

      <div className="relative h-60 w-full overflow-hidden bg-[#0a0b10] select-none" ref={containerRef}>
        {loading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/50">
            <div className="flex items-center gap-2 rounded-lg border border-white/10 bg-black/80 px-3 py-1.5 font-mono text-xs text-zinc-300">
              <div className="size-3 animate-spin rounded-full border-2 border-violet-400 border-t-transparent" />
              <span>Loading 3D asset...</span>
            </div>
          </div>
        )}

        <div className="pointer-events-none absolute right-2 bottom-2 rounded bg-black/60 px-2 py-0.5 text-[0.62rem] text-zinc-400 backdrop-blur-xs">
          Drag to spin • Scroll to zoom
        </div>
      </div>

      <div className="flex items-center justify-between border-t border-(--ui-border) bg-(--ui-panel-background)/40 px-3 py-2 text-xs">
        <button
          className="flex cursor-pointer items-center gap-1.5 font-medium text-violet-400 transition-colors hover:text-violet-300"
          onClick={handleRefineInChat}
          title="Refine this model with another prompt in chat"
          type="button"
        >
          <Zap className="size-3.5" />
          <span>Iterate in Chat</span>
        </button>

        <div className="flex items-center gap-2">
          {resolvedUrl && (
            <a
              className="flex items-center gap-1 rounded-md border border-(--ui-border) px-2.5 py-1 text-xs transition-colors hover:bg-(--ui-hover)"
              download={modelData?.filename || `model.${resolvedFormat}`}
              href={resolvedUrl}
            >
              <Download className="size-3" />
              <span>Download {resolvedFormat.toUpperCase()}</span>
            </a>
          )}

          <button
            className="flex cursor-pointer items-center gap-1 rounded-md bg-violet-600 px-3 py-1 text-xs font-semibold text-white shadow-xs transition-colors hover:bg-violet-500"
            onClick={handleOpenStudio}
            title="Open in full 3D Blender Studio"
            type="button"
          >
            <span>Open in Studio</span>
            <ExternalLink className="size-3" />
          </button>
        </div>
      </div>
    </div>
  )
}
