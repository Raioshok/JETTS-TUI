import { Loader } from '@jetts-tui/plugin-sdk'
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js'

import type { CameraAngle, ModelFileFormat, ModelStats, ShadingMode } from './types'

export interface ViewportHandle {
  resetCamera: (angle?: CameraAngle) => void
  takeSnapshot: () => null | string
}

interface ViewportProps {
  autoRotate: boolean
  lightIntensity: number
  modelFormat?: ModelFileFormat
  modelUrl: null | string
  onError?: (err: string) => void
  onLoadEnd?: () => void
  onLoadStart?: () => void
  onStatsChange?: (stats: ModelStats) => void
  shadingMode: ShadingMode
  showAxes: boolean
  showGrid: boolean
}

function applyShadingToObject(root: any, mode: ShadingMode): void {
  root.traverse((child: any) => {
    if (!child.isMesh) {
      return
    }

    if (mode === 'wireframe') {
      child.material = new THREE.MeshBasicMaterial({
        color: 0x00ffcc,
        wireframe: true
      })
    } else if (mode === 'normal') {
      child.material = new THREE.MeshNormalMaterial()
    } else if (mode === 'matcap') {
      child.material = new THREE.MeshStandardMaterial({
        color: 0x999999,
        metalness: 0.7,
        roughness: 0.3
      })
    } else if (child.userData.originalMaterial) {
      child.material = child.userData.originalMaterial
    }
  })
}

export const BlenderViewport = forwardRef<ViewportHandle, ViewportProps>(function BlenderViewport(
  {
    autoRotate,
    lightIntensity,
    modelFormat = 'glb',
    modelUrl,
    onError,
    onLoadEnd,
    onLoadStart,
    onStatsChange,
    shadingMode,
    showAxes,
    showGrid
  },
  ref
) {
  const containerRef = useRef<HTMLDivElement>(null)

  const engineRef = useRef<{
    animFrameId: null | number
    axesHelper: any
    camera: any
    controls: any
    currentModel: any
    defaultMesh: any
    gridHelper: any
    lightsGroup: any
    renderer: any
    scene: any
  }>({
    animFrameId: null,
    axesHelper: null,
    camera: null,
    controls: null,
    currentModel: null,
    defaultMesh: null,
    gridHelper: null,
    lightsGroup: null,
    renderer: null,
    scene: null
  })

  const [loading, setLoading] = useState(false)

  const resetCamera = useCallback((angle: CameraAngle = 'iso') => {
    const { camera, controls } = engineRef.current

    if (!camera || !controls) {
      return
    }

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

  const takeSnapshot = useCallback((): null | string => {
    const { camera, renderer, scene } = engineRef.current

    if (!renderer || !scene || !camera) {
      return null
    }

    renderer.render(scene, camera)

    return renderer.domElement.toDataURL('image/png')
  }, [])

  useImperativeHandle(
    ref,
    () => ({
      resetCamera,
      takeSnapshot
    }),
    [resetCamera, takeSnapshot]
  )

  useEffect(() => {
    const container = containerRef.current

    if (!container) {
      return
    }

    const engine = engineRef.current
    const width = container.clientWidth || 800
    const height = container.clientHeight || 600

    const scene = new THREE.Scene()
    engine.scene = scene

    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100)
    camera.position.set(3.2, 2.8, 3.2)
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
    renderer.toneMappingExposure = 1.1
    container.appendChild(renderer.domElement)
    engine.renderer = renderer

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.05
    controls.maxDistance = 25
    controls.minDistance = 0.5
    engine.controls = controls

    const lightsGroup = new THREE.Group()
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6)
    lightsGroup.add(ambientLight)

    const keyLight = new THREE.DirectionalLight(0xfff5e6, 1.2)
    keyLight.position.set(5, 8, 5)
    lightsGroup.add(keyLight)

    const fillLight = new THREE.DirectionalLight(0xddeeff, 0.6)
    fillLight.position.set(-6, 3, -4)
    lightsGroup.add(fillLight)

    const rimLight = new THREE.DirectionalLight(0xffeedd, 0.5)
    rimLight.position.set(0, 4, -6)
    lightsGroup.add(rimLight)

    scene.add(lightsGroup)
    engine.lightsGroup = lightsGroup

    const grid = new THREE.GridHelper(10, 20, 0x555566, 0x222233)
    grid.position.y = -0.01
    scene.add(grid)
    engine.gridHelper = grid

    const axes = new THREE.AxesHelper(1.5)
    axes.visible = false
    scene.add(axes)
    engine.axesHelper = axes

    const geom = new THREE.TorusKnotGeometry(0.8, 0.25, 100, 16)

    const mat = new THREE.MeshStandardMaterial({
      color: 0x8b5cf6,
      metalness: 0.8,
      roughness: 0.25
    })

    const defaultMesh = new THREE.Mesh(geom, mat)
    defaultMesh.position.y = 1.0
    scene.add(defaultMesh)
    engine.defaultMesh = defaultMesh

    let disposed = false
    let inViewport = true
    let pageVisible = typeof document === 'undefined' ? true : document.visibilityState === 'visible'

    const scheduleOrPause = () => {
      const shouldRun = !disposed && inViewport && pageVisible

      if (shouldRun && engine.animFrameId === null) {
        const animate = () => {
          if (disposed || !inViewport || !pageVisible) {
            engine.animFrameId = null

            return
          }

          engine.animFrameId = requestAnimationFrame(animate)

          if (engine.controls) {
            engine.controls.update()
          }

          if (engine.defaultMesh && !engine.currentModel) {
            engine.defaultMesh.rotation.y += 0.008
            engine.defaultMesh.rotation.x += 0.004
          }

          renderer.render(scene, camera)
        }

        engine.animFrameId = requestAnimationFrame(animate)
      } else if (!shouldRun && engine.animFrameId !== null) {
        cancelAnimationFrame(engine.animFrameId)
        engine.animFrameId = null
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
      const h = container.clientHeight

      if (w === 0 || h === 0) {
        return
      }

      engine.camera.aspect = w / h
      engine.camera.updateProjectionMatrix()
      engine.renderer.setSize(w, h)
    })

    resizeObserver.observe(container)

    return () => {
      disposed = true

      if (engine.animFrameId !== null) {
        cancelAnimationFrame(engine.animFrameId)
        engine.animFrameId = null
      }

      document.removeEventListener('visibilitychange', onVisibilityChange)
      intersectionObserver?.disconnect()
      resizeObserver.disconnect()
      geom.dispose()
      mat.dispose()
      controls.dispose()
      renderer.dispose()

      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement)
      }
    }
  }, [])

  useEffect(() => {
    const group = engineRef.current.lightsGroup

    if (!group) {
      return
    }

    group.children.forEach((light: any) => {
      if (light.isAmbientLight) {
        light.intensity = 0.6 * lightIntensity
      }

      if (light.isDirectionalLight) {
        light.intensity = 1.0 * lightIntensity
      }
    })
  }, [lightIntensity])

  useEffect(() => {
    if (engineRef.current.gridHelper) {
      engineRef.current.gridHelper.visible = showGrid
    }

    if (engineRef.current.axesHelper) {
      engineRef.current.axesHelper.visible = showAxes
    }
  }, [showAxes, showGrid])

  useEffect(() => {
    if (engineRef.current.controls) {
      engineRef.current.controls.autoRotate = autoRotate
    }
  }, [autoRotate])

  useEffect(() => {
    const engine = engineRef.current
    const scene = engine.scene

    if (!scene) {
      return
    }

    if (!modelUrl) {
      if (engine.currentModel) {
        scene.remove(engine.currentModel)
        engine.currentModel = null
      }

      if (engine.defaultMesh) {
        engine.defaultMesh.visible = true
      }

      onStatsChange?.({ meshes: 1, triangles: 3200, vertices: 1600 })

      return
    }

    let cancelled = false
    setLoading(true)
    onLoadStart?.()

    const mountLoadedObject = (rawModel: any) => {
      if (cancelled) {
        return
      }

      if (engine.currentModel) {
        scene.remove(engine.currentModel)
      }

      if (engine.defaultMesh) {
        engine.defaultMesh.visible = false
      }

      engine.currentModel = rawModel

      let vertices = 0
      let triangles = 0
      let meshes = 0

      rawModel.traverse((child: any) => {
        if (!child.isMesh) {
          return
        }

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

        if (!child.material) {
          child.material = new THREE.MeshStandardMaterial({
            color: 0xd4d4d8,
            metalness: 0.25,
            roughness: 0.45
          })
        }

        child.castShadow = true
        child.receiveShadow = true
        child.userData.originalMaterial = child.material
      })

      const box = new THREE.Box3().setFromObject(rawModel)
      const size = box.getSize(new THREE.Vector3())
      const center = box.getCenter(new THREE.Vector3())

      const maxDim = Math.max(size.x, size.y, size.z) || 1
      const scale = 2.4 / maxDim
      rawModel.scale.setScalar(scale)

      rawModel.position.x = -center.x * scale
      rawModel.position.y = -box.min.y * scale
      rawModel.position.z = -center.z * scale

      scene.add(rawModel)
      setLoading(false)
      onLoadEnd?.()

      onStatsChange?.({
        meshes,
        triangles: Math.round(triangles),
        vertices: Math.round(vertices)
      })

      resetCamera('iso')
    }

    const handleLoadError = (err: any) => {
      if (cancelled) {
        return
      }

      console.error('Failed to load 3D model:', err)
      setLoading(false)
      onError?.(err?.message || 'Failed to load model file')
    }

    const isObj = modelFormat === 'obj' || /\.obj(?:$|[?#])/i.test(modelUrl)

    if (isObj) {
      const objLoader = new OBJLoader()
      objLoader.load(modelUrl, mountLoadedObject, undefined, handleLoadError)
    } else {
      const gltfLoader = new GLTFLoader()
      gltfLoader.load(
        modelUrl,
        (gltf: any) => mountLoadedObject(gltf.scene || gltf.scenes[0]),
        undefined,
        handleLoadError
      )
    }

    return () => {
      cancelled = true
    }
  }, [modelFormat, modelUrl, onError, onLoadEnd, onLoadStart, onStatsChange, resetCamera])

  useEffect(() => {
    const model = engineRef.current.currentModel

    if (!model) {
      return
    }

    applyShadingToObject(model, shadingMode)
  }, [shadingMode])

  return (
    <div className="relative h-full w-full overflow-hidden select-none" ref={containerRef}>
      {loading && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/40 backdrop-blur-xs">
          <div className="flex flex-col items-center gap-2 rounded-xl border border-(--ui-stroke-tertiary) bg-(--ui-bg-elevated) p-4 shadow-lg">
            <Loader className="size-6" />
            <span className="font-mono text-xs text-(--ui-text-secondary)">Loading 3D asset…</span>
          </div>
        </div>
      )}
    </div>
  )
})
