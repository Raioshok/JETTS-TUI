import { beforeEach, describe, expect, it } from 'vitest'

import {
  $smart3DModalOpen,
  $smart3DModalScopes,
  clearAllSessionModels,
  getSessionModels,
  migrateDraftSessionModels,
  recordSessionModel,
  setSmart3DModalOpen
} from './blender-models'

describe('blender-models store', () => {
  beforeEach(() => {
    clearAllSessionModels()
  })

  it('migrates draft-keyed 3D models onto the created runtime session id without duplicates', () => {
    recordSessionModel('', {
      filename: 'tower.glb',
      format: 'glb',
      localPath: '/tmp/tower.glb',
      name: 'Medieval tower',
      prompt: 'medieval tower',
      sessionId: '__draft__',
      url: 'jettstui-media://stream/tower.glb'
    })

    expect(getSessionModels(null)).toHaveLength(1)
    migrateDraftSessionModels('sid-live-1')

    expect(getSessionModels(null)).toHaveLength(0)
    expect(getSessionModels('sid-live-1')).toHaveLength(1)
    expect(getSessionModels('sid-live-1')[0].sessionId).toBe('sid-live-1')
  })

  it('scopes Smart 3D modal open state per composer target so split tiles stay independent', () => {
    setSmart3DModalOpen(true, 'tile:stored-1')

    expect($smart3DModalScopes.get()['tile:stored-1']).toBe(true)
    expect($smart3DModalOpen.get()).toBe(false)

    setSmart3DModalOpen(true, 'main')
    expect($smart3DModalOpen.get()).toBe(true)

    clearAllSessionModels()
    expect($smart3DModalOpen.get()).toBe(false)
    expect($smart3DModalScopes.get()).toEqual({})
  })
})
