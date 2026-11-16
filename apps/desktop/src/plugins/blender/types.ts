export type RenderPreset = 'auto' | 'nature' | 'architecture' | 'scifi' | 'furniture' | 'abstract'

export type RenderQuality = 'draft' | 'final'

export type OutputFormat = 'glb' | 'png'

export type ShadingMode = 'textured' | 'wireframe' | 'normal' | 'matcap'

export type CameraAngle = 'iso' | 'front' | 'top' | 'side'

export interface ModelItem {
  filename: string
  url: string
  size_bytes: number
  modified_time: number
  format: string
}

export interface ModelStats {
  vertices: number
  triangles: number
  meshes: number
}

export interface BlenderStatus {
  available: boolean
  version: string
  path?: string | null
  output_dir?: string
}

export interface GenerateResponse {
  success: boolean
  filename: string
  url: string
  format: string
  size_bytes: number
  duration_seconds: number
  stdout?: string
}
