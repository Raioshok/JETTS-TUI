/* eslint-disable @typescript-eslint/no-explicit-any */
import React, { useEffect, useRef, useState, useCallback, useImperativeHandle, forwardRef } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'

import type { CameraAngle, ModelStats, ShadingMode } from './types'

export interface ViewportHandle {
  resetCamera: (angle?: CameraAngle) => void
  takeSnapshot: () => string | null
}

interface ViewportProps {
  modelUrl: string | null
  shadingMode: ShadingMode
  showGrid: boolean
  showAxes: boolean
  autoRotate: boolean
  lightIntensity: number
  onStatsChange?: (stats: ModelStats) => void
  onLoadStart?: () => void
  onLoadEnd?: () => void
  onError?: (err: string) => void
}

export const BlenderViewport = forwardRef<ViewportHandle, ViewportProps>(function BlenderViewport(
  {
    modelUrl,
    shadingMode,
    showGrid,
    showAxes,
    autoRotate,
    lightIntensity,
    onStatsChange,
    onLoadStart,
    onLoadEnd,
    onError
  },
  ref
) {
  const containerRef = useRef<HTMLDivElement>(null)
  const rendererRef = useRef<any>(null)
  const sceneRef = useRef<any>(null)
  const cameraRef = useRef<any>(null)
  const controlsRef = useRef<any>(null)
  const currentModelRef = useRef<any>(null)
  const defaultMeshRef = useRef<any>(null)
  const gridHelperRef = useRef<any>(null)
  const axesHelperRef = useRef<any>(null)
  const lightsGroupRef = useRef<any>(null)
  const animFrameIdRef = useRef<number | null>(null)

  const [loading, setLoading] = useState(false)

  // Camera reset imperative handler
  const resetCamera = useCallback((angle: CameraAngle = 'iso') => {
    const camera = cameraRef.current
    const controls = controlsRef.current
    if (!camera || !controls) return

    controls.target.set(0, 0, 0)
    const dist = 4.2

    switch (angle) {
      case 'front':
        camera.position.set(0, 0, dist)
        break
      case 'top':
        camera.position.set(0, dist, 0.001)
        break
      case 'side':
        camera.position.set(dist, 0, 0)
        break
      case 'iso':
      default:
        camera.position.set(dist * 0.7, dist * 0.6, dist * 0.7)
        break
    }
    camera.lookAt(0, 0, 0)
    controls.update()
  }, [])

  // Snapshot capture handler
  const takeSnapshot = useCallback((): string | null => {
    const renderer = rendererRef.current
    const scene = sceneRef.current
    const camera = cameraRef.current
    if (!renderer || !scene || !camera) return null

    renderer.render(scene, camera)
    return renderer.domElement.toDataURL('image/png')
  }, [])

  useImperativeHandle(ref, () => ({
    resetCamera,
    takeSnapshot
  }), [resetCamera, takeSnapshot])

  // Initialize Three.js scene
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const width = container.clientWidth || 800
    const height = container.clientHeight || 600

    // 1. Scene
    const scene = new THREE.Scene()
    sceneRef.current = scene

    // 2. Camera
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100)
    camera.position.set(3.2, 2.8, 3.2)
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
    renderer.toneMappingExposure = 1.1
    container.appendChild(renderer.domElement)
    rendererRef.current = renderer

    // 4. Controls
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.05
    controls.maxDistance = 25
    controls.minDistance = 0.5
    controlsRef.current = controls

    // 5. Lighting
    const lightsGroup = new THREE.Group()
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6 * lightIntensity)
    lightsGroup.add(ambientLight)

    const keyLight = new THREE.DirectionalLight(0xfff5e6, 1.2 * lightIntensity)
    keyLight.position.set(5, 8, 5)
    lightsGroup.add(keyLight)

    const fillLight = new THREE.DirectionalLight(0xddeeff, 0.6 * lightIntensity)
    fillLight.position.set(-6, 3, -4)
    lightsGroup.add(fillLight)

    const rimLight = new THREE.DirectionalLight(0xffeedd, 0.5 * lightIntensity)
    rimLight.position.set(0, 4, -6)
    lightsGroup.add(rimLight)

    scene.add(lightsGroup)
    lightsGroupRef.current = lightsGroup

    // 6. Helpers (Grid and Axes)
    const grid = new THREE.GridHelper(10, 20, 0x555566, 0x222233)
    grid.position.y = -0.01
    scene.add(grid)
    gridHelperRef.current = grid

    const axes = new THREE.AxesHelper(1.5)
    scene.add(axes)
    axesHelperRef.current = axes

    // 7. Default Preview Mesh (Geometric Sculpture)
    const geom = new THREE.TorusKnotGeometry(0.8, 0.25, 100, 16)
    const mat = new THREE.MeshStandardMaterial({
      color: 0x8b5cf6,
      roughness: 0.25,
      metalness: 0.8
    })
    const defaultMesh = new THREE.Mesh(geom, mat)
    defaultMesh.position.y = 1.0
    scene.add(defaultMesh)
    defaultMeshRef.current = defaultMesh

    // 8. Animation Loop
    let isRunning = true
    const animate = () => {
      if (!isRunning) return
      animFrameIdRef.current = requestAnimationFrame(animate)

      if (controlsRef.current) {
        controlsRef.current.autoRotate = autoRotate
        controlsRef.current.update()
      }

      if (defaultMeshRef.current && !currentModelRef.current) {
        defaultMeshRef.current.rotation.y += 0.008
        defaultMeshRef.current.rotation.x += 0.004
      }

      renderer.render(scene, camera)
    }
    animate()

    // 9. Resize Observer
    const resizeObserver = new ResizeObserver(() => {
      if (!container || !rendererRef.current || !cameraRef.current) return
      const w = container.clientWidth
      const h = container.clientHeight
      if (w === 0 || h === 0) return
      cameraRef.current.aspect = w / h
      cameraRef.current.updateProjectionMatrix()
      rendererRef.current.setSize(w, h)
    })
    resizeObserver.observe(container)

    // Cleanup
    return () => {
      isRunning = false
      if (animFrameIdRef.current) {
        cancelAnimationFrame(animFrameIdRef.current)
      }
      resizeObserver.disconnect()
      controls.dispose()
      renderer.dispose()
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement)
      }
    }
  }, [])

  // Update light intensity
  useEffect(() => {
    if (!lightsGroupRef.current) return
    const group = lightsGroupRef.current
    group.children.forEach((light: any) => {
      if (light.isAmbientLight) light.intensity = 0.6 * lightIntensity
      if (light.isDirectionalLight) light.intensity = 1.0 * lightIntensity
    })
  }, [lightIntensity])

  // Update grid & axes visibility
  useEffect(() => {
    if (gridHelperRef.current) gridHelperRef.current.visible = showGrid
    if (axesHelperRef.current) axesHelperRef.current.visible = showAxes
  }, [showGrid, showAxes])

  // Update auto rotate
  useEffect(() => {
    if (controlsRef.current) {
      controlsRef.current.autoRotate = autoRotate
    }
  }, [autoRotate])

  // Load Model from modelUrl
  useEffect(() => {
    const scene = sceneRef.current
    if (!scene) return

    // If no modelUrl, restore default procedural mesh
    if (!modelUrl) {
      if (currentModelRef.current) {
        scene.remove(currentModelRef.current)
        currentModelRef.current = null
      }
      if (defaultMeshRef.current) {
        defaultMeshRef.current.visible = true
      }
      onStatsChange?.({ vertices: 1600, triangles: 3200, meshes: 1 })
      return
    }

    setLoading(true)
    onLoadStart?.()

    const loader = new GLTFLoader()

    loader.load(
      modelUrl,
      (gltf: any) => {
        // Remove prior model & hide placeholder
        if (currentModelRef.current) {
          scene.remove(currentModelRef.current)
        }
        if (defaultMeshRef.current) {
          defaultMeshRef.current.visible = false
        }

        const model = gltf.scene || gltf.scenes[0]
        currentModelRef.current = model

        // Calculate statistics & normalize size
        let vertices = 0
        let triangles = 0
        let meshes = 0

        model.traverse((child: any) => {
          if (child.isMesh) {
            meshes++
            const geom = child.geometry
            if (geom) {
              if (geom.attributes.position) {
                vertices += geom.attributes.position.count
              }
              if (geom.index) {
                triangles += geom.index.count / 3
              } else if (geom.attributes.position) {
                triangles += geom.attributes.position.count / 3
              }
            }
            child.castShadow = true
            child.receiveShadow = true
            // Save original materials for shading toggle
            child.userData.originalMaterial = child.material
          }
        })

        // Center and scale model
        const box = new THREE.Box3().setFromObject(model)
        const size = box.getSize(new THREE.Vector3())
        const center = box.getCenter(new THREE.Vector3())

        const maxDim = Math.max(size.x, size.y, size.z) || 1
        const scale = 2.4 / maxDim
        model.scale.setScalar(scale)

        // Re-center after scale
        model.position.x = -center.x * scale
        model.position.y = -box.min.y * scale // Stand on floor
        model.position.z = -center.z * scale

        scene.add(model)
        setLoading(false)
        onLoadEnd?.()

        onStatsChange?.({
          vertices: Math.round(vertices),
          triangles: Math.round(triangles),
          meshes
        })

        // Auto-frame camera
        resetCamera('iso')
      },
      undefined,
      (err: any) => {
        console.error('Failed to load 3D model:', err)
        setLoading(false)
        onError?.(err?.message || 'Failed to load model file')
      }
    )
  }, [modelUrl, onLoadStart, onLoadEnd, onError, onStatsChange, resetCamera])

  // Handle Shading Mode changes
  useEffect(() => {
    const model = currentModelRef.current
    if (!model) return

    model.traverse((child: any) => {
      if (child.isMesh) {
        if (shadingMode === 'wireframe') {
          child.material = new THREE.MeshBasicMaterial({
            color: 0x00ffcc,
            wireframe: true
          })
        } else if (shadingMode === 'normal') {
          child.material = new THREE.MeshNormalMaterial()
        } else if (shadingMode === 'matcap') {
          child.material = new THREE.MeshStandardMaterial({
            color: 0x999999,
            roughness: 0.3,
            metalness: 0.7
          })
        } else {
          // restore textured
          if (child.userData.originalMaterial) {
            child.material = child.userData.originalMaterial
          }
        }
      }
    })
  }, [shadingMode])

  return (
    <div className="relative h-full w-full overflow-hidden select-none" ref={containerRef}>
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/40 backdrop-blur-xs z-20">
          <div className="flex flex-col items-center gap-2 rounded-xl bg-(--ui-background)/90 p-4 border border-(--ui-border) shadow-xl">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-violet-500 border-t-transparent" />
            <span className="text-xs font-mono text-(--ui-text-secondary)">Loading 3D asset...</span>
          </div>
        </div>
      )}
    </div>
  )
})
