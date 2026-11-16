/* eslint-disable @typescript-eslint/no-explicit-any */
'use client'

import React, { FC, useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'

import { requestComposerInsert } from '@/app/chat/composer/focus'
import { Box, Download, Eye, Layers3, RefreshCw, Zap, ExternalLink } from '@/lib/icons'
import { blenderModelFromResult, resolveModelDisplayUrl, type BlenderModelResultData } from '@/lib/generated-models'
import { cn } from '@/lib/utils'

interface GeneratedModelProps {
  args?: Record<string, unknown>
  result?: unknown
  modelUrl?: string
  title?: string
}

export const GeneratedModelResult: FC<GeneratedModelProps> = ({ args, result, modelUrl, title }) => {
  const containerRef = useRef<HTMLDivElement>(null)
  const rendererRef = useRef<any>(null)
  const sceneRef = useRef<any>(null)
  const cameraRef = useRef<any>(null)
  const controlsRef = useRef<any>(null)
  const modelGroupRef = useRef<any>(null)
  const animIdRef = useRef<number | null>(null)

  const isPending = result === undefined && !modelUrl
  const modelData: BlenderModelResultData | null = result !== undefined ? blenderModelFromResult(result) : null

  const resolvedUrl = modelUrl || modelData?.displayUrl || ''
  const displayTitle = title || modelData?.prompt || (typeof args?.prompt === 'string' ? args.prompt : '3D Model')
  const isImageStill = modelData?.format === 'png'

  const [wireframe, setWireframe] = useState(false)
  const [autoRotate, setAutoRotate] = useState(true)
  const [loading, setLoading] = useState(true)
  const [stats, setStats] = useState({ verts: 0, tris: 0 })

  // Initialize Three.js viewport for the model card
  useEffect(() => {
    if (isPending || isImageStill || !resolvedUrl) return

    const container = containerRef.current
    if (!container) return

    const width = container.clientWidth || 480
    const height = 240

    // 1. Scene
    const scene = new THREE.Scene()
    sceneRef.current = scene

    // 2. Camera
    const camera = new THREE.PerspectiveCamera(40, width / height, 0.1, 50)
    camera.position.set(2.8, 2.2, 2.8)
    cameraRef.current = camera

    // 3. WebGLRenderer
    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
      preserveDrawingBuffer: true,
      powerPreference: 'high-performance'
    })
    renderer.setSize(width, height)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    container.appendChild(renderer.domElement)
    rendererRef.current = renderer

    // 4. Controls
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.05
    controls.maxDistance = 15
    controls.minDistance = 0.8
    controls.autoRotate = autoRotate
    controls.autoRotateSpeed = 2.0
    controlsRef.current = controls

    // 5. Studio Lighting
    const ambient = new THREE.AmbientLight(0xffffff, 0.7)
    scene.add(ambient)

    const keyLight = new THREE.DirectionalLight(0xfff5e6, 1.2)
    keyLight.position.set(4, 6, 4)
    scene.add(keyLight)

    const fillLight = new THREE.DirectionalLight(0xddeeff, 0.5)
    fillLight.position.set(-5, 2, -3)
    scene.add(fillLight)

    // 6. Grid Helper (Subtle)
    const grid = new THREE.GridHelper(6, 12, 0x444455, 0x222233)
    grid.position.y = -0.01
    scene.add(grid)

    // 7. Load GLB Model
    const loader = new GLTFLoader()
    setLoading(true)

    loader.load(
      resolvedUrl,
      (gltf: any) => {
        const model = gltf.scene || gltf.scenes[0]
        modelGroupRef.current = model

        let verts = 0
        let tris = 0

        model.traverse((child: any) => {
          if (child.isMesh) {
            child.userData.origMat = child.material
            const geom = child.geometry
            if (geom) {
              if (geom.attributes.position) verts += geom.attributes.position.count
              if (geom.index) tris += geom.index.count / 3
              else if (geom.attributes.position) tris += geom.attributes.position.count / 3
            }
          }
        })

        // Center and normalize scale
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
        setStats({ verts: Math.round(verts), tris: Math.round(tris) })
        setLoading(false)

        controls.target.set(0, 0.5, 0)
        camera.position.set(2.8, 2.0, 2.8)
        camera.lookAt(0, 0.5, 0)
        controls.update()
      },
      undefined,
      (err: any) => {
        console.error('Failed to load in-chat GLB:', err)
        setLoading(false)
      }
    )

    // 8. Animation Loop
    let running = true
    const animate = () => {
      if (!running) return
      animIdRef.current = requestAnimationFrame(animate)
      if (controlsRef.current) {
        controlsRef.current.autoRotate = autoRotate
        controlsRef.current.update()
      }
      renderer.render(scene, camera)
    }
    animate()

    // 9. Resize Observer
    const resizeObserver = new ResizeObserver(() => {
      if (!container || !rendererRef.current || !cameraRef.current) return
      const w = container.clientWidth
      if (w === 0) return
      cameraRef.current.aspect = w / height
      cameraRef.current.updateProjectionMatrix()
      rendererRef.current.setSize(w, height)
    })
    resizeObserver.observe(container)

    return () => {
      running = false
      if (animIdRef.current) cancelAnimationFrame(animIdRef.current)
      resizeObserver.disconnect()
      controls.dispose()
      renderer.dispose()
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement)
      }
    }
  }, [isPending, isImageStill, resolvedUrl])

  // Toggle wireframe
  useEffect(() => {
    if (!modelGroupRef.current) return
    modelGroupRef.current.traverse((child: any) => {
      if (child.isMesh) {
        if (wireframe) {
          child.material = new THREE.MeshBasicMaterial({ color: 0x00ffcc, wireframe: true })
        } else if (child.userData.origMat) {
          child.material = child.userData.origMat
        }
      }
    })
  }, [wireframe])

  // Toggle auto rotate
  useEffect(() => {
    if (controlsRef.current) {
      controlsRef.current.autoRotate = autoRotate
    }
  }, [autoRotate])

  // Snapshot capture
  const handleSnapshot = () => {
    if (!rendererRef.current || !sceneRef.current || !cameraRef.current) return
    rendererRef.current.render(sceneRef.current, cameraRef.current)
    const dataUrl = rendererRef.current.domElement.toDataURL('image/png')
    const link = document.createElement('a')
    link.download = `${modelData?.filename || 'model'}_preview.png`
    link.href = dataUrl
    link.click()
  }

  // Handle Iterative Prompt insertion in Chat
  const handleRefineInChat = () => {
    const promptRefine = `Refine 3D model (${displayTitle}): `
    requestComposerInsert(promptRefine)
  }

  // Open in full 3D studio
  const handleOpenStudio = () => {
    window.location.hash = '#/blender'
  }

  // Render Pending Generation State
  if (isPending) {
    return (
      <div className="my-2.5 max-w-xl rounded-xl border border-violet-500/30 bg-(--ui-surface-background)/90 p-4 shadow-xl backdrop-blur-md">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className="flex size-6 items-center justify-center rounded-md bg-violet-600/20 text-violet-400 border border-violet-500/30">
              <Box className="size-3.5 animate-pulse" />
            </span>
            <span className="text-xs font-semibold text-(--ui-text-primary)">Blender 3D Generator</span>
          </div>
          <span className="text-[0.68rem] font-mono text-violet-400 animate-pulse">Running headless bpy...</span>
        </div>

        <div className="h-44 w-full rounded-lg border border-dashed border-violet-500/30 bg-black/40 flex flex-col items-center justify-center gap-3">
          <div className="relative flex size-12 items-center justify-center">
            <div className="absolute inset-0 rounded-full border-2 border-violet-500/20 animate-ping" />
            <div className="size-8 rounded-lg border border-violet-400 bg-violet-500/20 animate-spin" />
          </div>
          <span className="text-xs font-medium text-zinc-300">
            {typeof args?.prompt === 'string' ? args.prompt : 'Generating 3D asset...'}
          </span>
          <span className="text-[0.68rem] text-zinc-500 font-mono">Building geometry, shaders & lighting</span>
        </div>
      </div>
    )
  }

  // Render Still Image Render Result (PNG mode)
  if (isImageStill && resolvedUrl) {
    return (
      <div className="my-2.5 max-w-xl rounded-xl border border-(--ui-border) bg-(--ui-surface-background)/90 overflow-hidden shadow-xl">
        <div className="flex items-center justify-between border-b border-(--ui-border) px-3 py-2 bg-(--ui-panel-background)/50">
          <div className="flex items-center gap-2 truncate">
            <Box className="size-3.5 text-violet-400 shrink-0" />
            <span className="text-xs font-medium truncate">{displayTitle}</span>
          </div>
          <span className="text-[0.65rem] font-mono px-2 py-0.5 rounded bg-violet-500/10 text-violet-300 border border-violet-500/20">
            PNG Render
          </span>
        </div>
        <div className="p-3 bg-black/40 flex justify-center">
          <img src={resolvedUrl} alt={displayTitle} className="max-h-72 rounded-lg object-contain" />
        </div>
        <div className="flex items-center justify-between border-t border-(--ui-border) px-3 py-2 bg-(--ui-panel-background)/40 text-xs">
          <button
            onClick={handleRefineInChat}
            className="flex items-center gap-1 text-violet-400 hover:text-violet-300 cursor-pointer"
          >
            <Zap className="size-3.5" />
            <span>Refine in Chat</span>
          </button>
          <a
            href={resolvedUrl}
            download="render.png"
            className="flex items-center gap-1 px-2.5 py-1 rounded bg-violet-600 hover:bg-violet-500 text-white font-medium"
          >
            <Download className="size-3.5" />
            <span>Download PNG</span>
          </a>
        </div>
      </div>
    )
  }

  // Render Interactive 3D Model Card
  return (
    <div className="my-2.5 max-w-xl rounded-xl border border-(--ui-border) bg-(--ui-surface-background)/95 overflow-hidden shadow-2xl backdrop-blur-md">
      {/* Card Header */}
      <div className="flex items-center justify-between border-b border-(--ui-border) px-3.5 py-2.5 bg-(--ui-panel-background)/60">
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-violet-600/20 text-violet-400 border border-violet-500/30">
            <Box className="size-3.5" />
          </span>
          <div className="min-w-0">
            <div className="text-xs font-semibold truncate text-(--ui-text-primary)">
              {displayTitle}
            </div>
            {stats.verts > 0 && (
              <div className="text-[0.65rem] font-mono text-zinc-400 flex items-center gap-2">
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

        {/* Viewport Action Controls */}
        <div className="flex items-center gap-1">
          <button
            onClick={() => setWireframe(!wireframe)}
            className={cn(
              'p-1.5 rounded-md border text-xs transition-colors cursor-pointer',
              wireframe
                ? 'border-violet-500/50 bg-violet-500/15 text-violet-300'
                : 'border-(--ui-border) text-(--ui-text-tertiary) hover:text-(--ui-text-primary)'
            )}
            title="Toggle Wireframe"
          >
            <Layers3 className="size-3.5" />
          </button>

          <button
            onClick={() => setAutoRotate(!autoRotate)}
            className={cn(
              'p-1.5 rounded-md border text-xs transition-colors cursor-pointer',
              autoRotate
                ? 'border-violet-500/50 bg-violet-500/15 text-violet-300'
                : 'border-(--ui-border) text-(--ui-text-tertiary) hover:text-(--ui-text-primary)'
            )}
            title="Toggle Turntable Rotation"
          >
            <RefreshCw className={cn('size-3.5', autoRotate && 'animate-spin')} />
          </button>

          <button
            onClick={handleSnapshot}
            className="p-1.5 rounded-md border border-(--ui-border) text-(--ui-text-tertiary) hover:text-(--ui-text-primary) cursor-pointer"
            title="Take Snapshot"
          >
            <Eye className="size-3.5" />
          </button>
        </div>
      </div>

      {/* 3D WebGL Canvas Viewport */}
      <div className="relative h-60 w-full bg-[#0a0b10] overflow-hidden select-none" ref={containerRef}>
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/50 z-10">
            <div className="flex items-center gap-2 rounded-lg bg-black/80 px-3 py-1.5 border border-white/10 text-xs font-mono text-zinc-300">
              <div className="size-3 animate-spin rounded-full border-2 border-violet-400 border-t-transparent" />
              <span>Loading 3D asset...</span>
            </div>
          </div>
        )}

        {/* Orbit hint overlay */}
        <div className="absolute bottom-2 right-2 rounded bg-black/60 px-2 py-0.5 text-[0.62rem] text-zinc-400 backdrop-blur-xs pointer-events-none">
          Drag to spin • Scroll to zoom
        </div>
      </div>

      {/* Card Footer Actions */}
      <div className="flex items-center justify-between border-t border-(--ui-border) px-3 py-2 bg-(--ui-panel-background)/40 text-xs">
        <button
          onClick={handleRefineInChat}
          className="flex items-center gap-1.5 text-violet-400 hover:text-violet-300 font-medium cursor-pointer transition-colors"
          title="Refine this model with another prompt in chat"
        >
          <Zap className="size-3.5" />
          <span>Iterate in Chat</span>
        </button>

        <div className="flex items-center gap-2">
          {resolvedUrl && (
            <a
              href={resolvedUrl}
              download={modelData?.filename || 'model.glb'}
              className="flex items-center gap-1 px-2.5 py-1 rounded-md border border-(--ui-border) hover:bg-(--ui-hover) text-xs transition-colors"
            >
              <Download className="size-3" />
              <span>Download GLB</span>
            </a>
          )}

          <button
            onClick={handleOpenStudio}
            className="flex items-center gap-1 px-3 py-1 rounded-md bg-violet-600 hover:bg-violet-500 text-white text-xs font-semibold shadow-xs transition-colors cursor-pointer"
            title="Open in full 3D Blender Studio"
          >
            <span>Open in Studio</span>
            <ExternalLink className="size-3" />
          </button>
        </div>
      </div>
    </div>
  )
}
