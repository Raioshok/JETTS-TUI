export type RenderPreset = 'abstract' | 'architecture' | 'auto' | 'furniture' | 'nature' | 'scifi'

export type RenderQuality = 'draft' | 'final'

export type OutputFormat = 'glb' | 'png'

export type ModelFileFormat = 'glb' | 'gltf' | 'obj' | 'png'

export type ShadingMode = 'matcap' | 'normal' | 'textured' | 'wireframe'

export type CameraAngle = 'front' | 'iso' | 'side' | 'top'

export interface ModelItem {
  filename: string
  format: string
  modified_time: number
  path?: string
  size_bytes: number
  url: string
}

export interface ModelStats {
  meshes: number
  triangles: number
  vertices: number
}

export interface BlenderStatus {
  available: boolean
  output_dir?: string
  path?: null | string
  version: string
}

export interface GenerateResponse {
  duration_seconds: number
  filename: string
  format: string
  path?: string
  size_bytes: number
  stdout?: string
  success: boolean
  url: string
}
