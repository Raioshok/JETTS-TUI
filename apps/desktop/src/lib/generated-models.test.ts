import { describe, expect, it } from 'vitest'

import { blenderModelFromResult, resolveModelDisplayUrl } from './generated-models'
import { $session3DModels, clearSessionModels, getSessionModels, recordSessionModel } from '@/store/blender-models'

describe('generated-models and session 3D context', () => {
  it('resolves model display URLs properly', () => {
    expect(resolveModelDisplayUrl('http://example.com/mesh.glb')).toBe('http://example.com/mesh.glb')
    expect(resolveModelDisplayUrl('blob:http://localhost/123')).toBe('blob:http://localhost/123')
    expect(resolveModelDisplayUrl('C:\\Users\\test\\.jettstui\\models\\tree.glb')).toBe(
      '/api/plugins/blender/files/tree.glb'
    )
    expect(resolveModelDisplayUrl('scifi_reactor.glb')).toBe('/api/plugins/blender/files/scifi_reactor.glb')
  })

  it('parses blender_render tool results', () => {
    const rawResult = JSON.stringify({
      success: true,
      prompt: 'A stylized pine tree',
      format: 'glb',
      output_path: 'C:/models/pine_tree.glb',
      filename: 'pine_tree.glb',
      file_size_bytes: 45000,
      duration_seconds: 2.4
    })

    const parsed = blenderModelFromResult(rawResult)
    expect(parsed).not.toBeNull()
    expect(parsed?.success).toBe(true)
    expect(parsed?.prompt).toBe('A stylized pine tree')
    expect(parsed?.format).toBe('glb')
    expect(parsed?.filename).toBe('pine_tree.glb')
    expect(parsed?.displayUrl).toBe('/api/plugins/blender/files/pine_tree.glb')
  })

  it('handles and ignores failed tool results', () => {
    const failedResult = JSON.stringify({
      success: false,
      error: 'Blender not found'
    })

    const parsed = blenderModelFromResult(failedResult)
    expect(parsed).toBeNull()
  })

  it('records and retrieves session 3D models', () => {
    const sessionId = 'test-session-123'
    clearSessionModels(sessionId)

    expect(getSessionModels(sessionId)).toEqual([])

    recordSessionModel(sessionId, {
      sessionId,
      filename: 'cabin.glb',
      name: 'Cozy Cabin',
      url: '/api/plugins/blender/files/cabin.glb',
      localPath: '/tmp/cabin.glb',
      format: 'glb',
      prompt: 'A cozy mountain cabin',
      sizeBytes: 120000
    })

    const list = getSessionModels(sessionId)
    expect(list.length).toBe(1)
    expect(list[0].filename).toBe('cabin.glb')
    expect(list[0].prompt).toBe('A cozy mountain cabin')

    // Clean up
    clearSessionModels(sessionId)
    expect(getSessionModels(sessionId)).toEqual([])
  })
})
