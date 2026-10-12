import { atom } from 'nanostores'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { JettsTUIConnection } from '@/global'
import type { ProfileInfo } from '@/types/jettstui'

// Keep profile.ts's side-effecting imports inert: the gateway socket layer and
// the REST query client must not run for real in a unit test.
const ensureGatewayForProfile = vi.fn(async () => undefined)
const openGatewayForProfile = vi.fn(async (_profile: string) => undefined)
const $gateway = atom<unknown>({ id: 'live-socket' })
const resetStarmapGraph = vi.fn()

vi.mock('@/store/gateway', () => ({ $gateway, ensureGatewayForProfile, openGatewayForProfile }))
vi.mock('@/jettstui', () => ({
  getProfiles: vi.fn(async () => ({ profiles: [] })),
  setApiRequestProfile: vi.fn()
}))
vi.mock('@/lib/query-client', () => ({ invalidateProfileScopedQueries: vi.fn() }))
vi.mock('@/store/starmap', () => ({ resetStarmapGraph }))

const {
  $activeGatewayProfile,
  $newChatProfile,
  $profiles,
  ensureGatewayProfile,
  prepareProfileFollow,
  prewarmProfileBackend,
  refreshProfiles
} = await import('./profile')

const { $connection } = await import('./session')
const { invalidateProfileScopedQueries } = await import('@/lib/query-client')
const { getProfiles } = await import('@/jettstui')

const profile = (name: string, isDefault = false): ProfileInfo => ({
  has_env: false,
  is_default: isDefault,
  model: null,
  name,
  path: `/tmp/jettstui/${name}`,
  provider: null,
  skill_count: 0
})

const remoteConn = (over: Partial<JettsTUIConnection> = {}): JettsTUIConnection =>
  ({ baseUrl: 'https://jettstui-roy.tail.ts.net', mode: 'remote', profile: 'vps-remote', ...over }) as JettsTUIConnection

const localConn = (over: Partial<JettsTUIConnection> = {}): JettsTUIConnection =>
  ({ baseUrl: '', mode: 'local', profile: 'default', ...over }) as JettsTUIConnection

const getConnection = vi.fn<(profile?: string | null) => Promise<JettsTUIConnection>>()

beforeEach(() => {
  getConnection.mockReset()
  ensureGatewayForProfile.mockClear()
  openGatewayForProfile.mockClear()
  $gateway.set({ id: 'live-socket' })
  $activeGatewayProfile.set('default')
  $connection.set(localConn())
  $profiles.set([])
  vi.stubGlobal('window', { jettstuiDesktop: { getConnection } })
  vi.mocked(invalidateProfileScopedQueries).mockClear()
  resetStarmapGraph.mockClear()
})

afterEach(() => {
  vi.unstubAllGlobals()
  $connection.set(null)
})

describe('ensureGatewayProfile → $connection sync (#46651)', () => {
  it('refreshes $connection to the remote descriptor when activating a remote pool profile', async () => {
    // Regression: the primary window backend is local, so $connection.mode is
    // "local". Activating the remote profile must flip it to "remote" — without
    // this, image attach uses path-based image.attach against the remote
    // gateway ("image not found: C:\\…") instead of image.attach_bytes.
    getConnection.mockResolvedValue(remoteConn())

    await ensureGatewayProfile('vps-remote')

    expect(ensureGatewayForProfile).toHaveBeenCalledWith('vps-remote')
    expect(getConnection).toHaveBeenCalledWith('vps-remote')
    expect($connection.get()?.mode).toBe('remote')
    expect($connection.get()?.profile).toBe('vps-remote')
  })

  it('resyncs $connection back to local when returning to the default profile', async () => {
    $activeGatewayProfile.set('vps-remote')
    $connection.set(remoteConn())
    getConnection.mockResolvedValue(localConn())

    await ensureGatewayProfile('default')

    expect(getConnection).toHaveBeenCalledWith('default')
    expect($connection.get()?.mode).toBe('local')
  })

  it('leaves the prior connection intact when the descriptor fetch fails', async () => {
    getConnection.mockRejectedValue(new Error('backend unreachable'))

    await ensureGatewayProfile('vps-remote')

    // Best-effort: boot/reconnect resyncs later; we must not null it out here.
    expect($connection.get()?.mode).toBe('local')
  })

  it('does not churn $connection when the target is already the active profile', async () => {
    $activeGatewayProfile.set('vps-remote')
    $connection.set(remoteConn())

    await ensureGatewayProfile('vps-remote')

    expect(getConnection).not.toHaveBeenCalled()
    expect(ensureGatewayForProfile).not.toHaveBeenCalled()
    expect($connection.get()?.mode).toBe('remote')
  })
})

describe('profile-scoped cache invalidation', () => {
  it('drops the memory graph cache when the active gateway profile changes', () => {
    $activeGatewayProfile.set('coder')

    expect(invalidateProfileScopedQueries).toHaveBeenCalled()
    expect(resetStarmapGraph).toHaveBeenCalledTimes(1)
  })
})

describe('prewarmProfileBackend (hover-intent pool spawn)', () => {
  it('opens the gateway (spawn + connect, no activation) for a non-active profile', () => {
    prewarmProfileBackend('warm-basic')

    expect(openGatewayForProfile).toHaveBeenCalledWith('warm-basic')
    // Pre-warm must never activate — that's the click's job.
    expect(ensureGatewayForProfile).not.toHaveBeenCalled()
  })

  it('skips the profile the gateway is already on', () => {
    $activeGatewayProfile.set('warm-active')

    prewarmProfileBackend('warm-active')

    expect(openGatewayForProfile).not.toHaveBeenCalled()
  })

  it('throttles repeat pre-warms for the same profile within the interval', () => {
    prewarmProfileBackend('warm-throttle-a')
    prewarmProfileBackend('warm-throttle-a')
    prewarmProfileBackend('warm-throttle-b')

    const calls = openGatewayForProfile.mock.calls.map(([name]) => name)
    expect(calls.filter(name => name === 'warm-throttle-a')).toHaveLength(1)
    expect(calls.filter(name => name === 'warm-throttle-b')).toHaveLength(1)
  })

  it('swallows spawn failures — error UX belongs to the real switch', () => {
    openGatewayForProfile.mockRejectedValueOnce(new Error('spawn failed'))

    expect(() => prewarmProfileBackend('warm-failing')).not.toThrow()
  })
})

describe('refreshProfiles shared rail list (#49289)', () => {
  it('removes a deleted profile from the shared $profiles cache after Manage Profiles refreshes', async () => {
    $profiles.set([profile('default', true), profile('test1')])
    vi.mocked(getProfiles).mockResolvedValueOnce({ profiles: [profile('default', true)] })

    await refreshProfiles()

    expect($profiles.get().map(profile => profile.name)).toEqual(['default'])
  })

  it('leaves the shared $profiles cache intact when the refresh fails', async () => {
    $profiles.set([profile('default', true), profile('test1')])
    vi.mocked(getProfiles).mockRejectedValueOnce(new Error('backend unavailable'))

    await expect(refreshProfiles()).rejects.toThrow('backend unavailable')

    expect($profiles.get().map(profile => profile.name)).toEqual(['default', 'test1'])
  })

  it('never lets a slow, older refresh put a pre-rename list back', async () => {
    // Panel-open refresh is slow; the post-rename refresh returns first.
    let releaseOld!: (value: { profiles: ProfileInfo[] }) => void
    vi.mocked(getProfiles)
      .mockImplementationOnce(() => new Promise(resolve => (releaseOld = resolve)))
      .mockResolvedValueOnce({ profiles: [profile('default', true), profile('work2')] })

    const older = refreshProfiles()
    const newer = refreshProfiles()

    expect((await newer).map(p => p.name)).toEqual(['default', 'work2'])
    releaseOld({ profiles: [profile('default', true), profile('work')] })

    // The stale response neither publishes nor reaches its own caller.
    expect((await older).map(p => p.name)).toEqual(['default', 'work2'])
    expect($profiles.get().map(p => p.name)).toEqual(['default', 'work2'])
  })
})

describe('prepareProfileFollow', () => {
  it('moves the live gateway and new-chat target off a deleted active profile to default', async () => {
    $activeGatewayProfile.set('work')
    $newChatProfile.set('work')
    getConnection.mockResolvedValue(localConn())

    const follow = prepareProfileFollow('work')
    follow(null)

    expect($newChatProfile.get()).toBe('default')
    await vi.waitFor(() => expect($activeGatewayProfile.get()).toBe('default'))
  })

  it('follows a rename of the active profile to the new name', () => {
    $activeGatewayProfile.set('work')
    $newChatProfile.set('work')

    prepareProfileFollow('work')('work2')

    expect($newChatProfile.get()).toBe('work2')
  })

  it('leaves everything alone when another profile changes', () => {
    $activeGatewayProfile.set('default')
    $newChatProfile.set('default')

    prepareProfileFollow('work')(null)

    expect($activeGatewayProfile.get()).toBe('default')
    expect($newChatProfile.get()).toBe('default')
  })
})

