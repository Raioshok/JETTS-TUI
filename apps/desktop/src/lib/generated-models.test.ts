import { afterEach, describe, expect, it } from 'vitest'

import { clearSessionModels, getSessionModels, recordSessionModel } from '@/store/blender-models'

import {
  blenderModelFromResult,
  detectModelFormat,
  resolveModelDisplayUrl,
  studioDeepLinkHash
} from './generated-models'

describe('generated-models and session 3D context', () => {
  afterEach(() => {
    Reflect.deleteProperty(window, 'jettstuiDesktop')
  })

  it('resolves model display URLs across web and desktop Electron stream protocol', () => {
    expect(resolveModelDisplayUrl('http://example.com/mesh.glb')).toBe('http://example.com/mesh.glb')
    expect(resolveModelDisplayUrl('blob:http://localhost/123')).toBe('blob:http://localhost/123')
    expect(resolveModelDisplayUrl('C:\\Users\\test\\.jettstui\\models\\tree.glb')).toBe(
      '/api/plugins/blender/files/tree.glb'
    )
    expect(resolveModelDisplayUrl('scifi_reactor.glb')).toBe('/api/plugins/blender/files/scifi_reactor.glb')

    Object.defineProperty(window, 'jettstuiDesktop', {
      configurable: true,
      value: {}
    })

    expect(resolveModelDisplayUrl('C:/models/chair.obj')).toBe('jettstui-media://stream/C%3A%2Fmodels%2Fchair.obj')
  })

  it('detects 3D and render formats including encoded media stream URLs', () => {
    expect(detectModelFormat('jettstui-media://stream/C%3A%2Fmodels%2Fstatue.obj')).toBe('obj')
    expect(detectModelFormat('/api/plugins/blender/files/scene.gltf?v=1')).toBe('gltf')
    expect(detectModelFormat('render_out.png')).toBe('png')
    expect(detectModelFormat('forest.glb')).toBe('glb')
  })

  it('builds Studio deep-link hashes with encoded query params', () => {
    const hash = studioDeepLinkHash({
      format: 'obj',
      localPath: 'C:/models/chair.obj',
      name: 'chair.obj',
      url: 'jettstui-media://stream/C%3A%2Fmodels%2Fchair.obj'
    })

    expect(hash).toContain('#/blender?')
    expect(hash).toContain('format=obj')
    expect(hash).toContain('name=chair.obj')
  })

  it('parses blender_render tool results purely without mutating stores', () => {
    const sessionId = 'pure-parse-check'
    clearSessionModels(sessionId)

    const rawResult = JSON.stringify({
      duration_seconds: 2.4,
      file_size_bytes: 45000,
      filename: 'pine_tree.glb',
      format: 'glb',
      output_path: 'C:/models/pine_tree.glb',
      prompt: 'A stylized pine tree',
      success: true
    })

    const parsed = blenderModelFromResult(rawResult)
    expect(parsed).not.toBeNull()
    expect(parsed?.success).toBe(true)
    expect(parsed?.prompt).toBe('A stylized pine tree')
    expect(parsed?.format).toBe('glb')
    expect(parsed?.filename).toBe('pine_tree.glb')
    expect(parsed?.displayUrl).toBe('/api/plugins/blender/files/pine_tree.glb')
    expect(getSessionModels(sessionId)).toEqual([])
  })

  it('ignores failed tool results and stdout-only script runs with no output file', () => {
    expect(
      blenderModelFromResult(
        JSON.stringify({
          error: 'Blender not found',
          success: false
        })
      )
    ).toBeNull()

    expect(
      blenderModelFromResult(
        JSON.stringify({
          duration_seconds: 0.3,
          output_exists: false,
          output_path: null,
          stdout: 'Mesh count: 2',
          success: true
        })
      )
    ).toBeNull()
  })

  it('records and retrieves session 3D models without duplicates', () => {
    const sessionId = 'test-session-123'
    clearSessionModels(sessionId)

    expect(getSessionModels(sessionId)).toEqual([])

    recordSessionModel(sessionId, {
      filename: 'cabin.glb',
      format: 'glb',
      localPath: '/tmp/cabin.glb',
      name: 'Cozy Cabin',
      prompt: 'A cozy mountain cabin',
      sessionId,
      sizeBytes: 120000,
      url: '/api/plugins/blender/files/cabin.glb'
    })

    recordSessionModel(sessionId, {
      filename: 'cabin.glb',
      format: 'glb',
      localPath: '/tmp/cabin.glb',
      name: 'Cozy Cabin',
      prompt: 'A cozy mountain cabin',
      sessionId,
      sizeBytes: 120000,
      url: '/api/plugins/blender/files/cabin.glb'
    })

    const list = getSessionModels(sessionId)
    expect(list.length).toBe(1)
    expect(list[0].filename).toBe('cabin.glb')
    expect(list[0].prompt).toBe('A cozy mountain cabin')

    clearSessionModels(sessionId)
    expect(getSessionModels(sessionId)).toEqual([])
  })
})
