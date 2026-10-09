import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { OAuthProvider } from '@/types/jettstui'

const api = vi.hoisted(() => ({
  cancelOAuthSession: vi.fn(),
  pollOAuthSession: vi.fn(),
  startOAuthLogin: vi.fn(),
  submitOAuthCode: vi.fn()
}))

vi.mock('@/jettstui', async importOriginal => ({
  ...(await importOriginal<object>()),
  ...api
}))

const { $desktopOnboarding, cancelOnboardingFlow, setOnboardingCode, startProviderOAuth, submitOnboardingCode } =
  await import('@/store/onboarding')

const provider: OAuthProvider = {
  cli_command: 'jettstui auth add antigravity',
  docs_url: 'https://antigravity.google/',
  flow: 'pkce',
  id: 'antigravity',
  name: 'Google Antigravity',
  status: { logged_in: false }
}

const ctx = { requestGateway: async () => undefined as never }

beforeEach(() => {
  vi.useFakeTimers()
  window.open = vi.fn() as typeof window.open
  api.cancelOAuthSession.mockResolvedValue({ ok: true })
  api.startOAuthLogin.mockResolvedValue({
    auth_url: 'https://accounts.google.com/o/oauth2/v2/auth',
    expires_in: 900,
    flow: 'pkce',
    session_id: 's1'
  })
})

afterEach(() => {
  cancelOnboardingFlow()
  vi.useRealTimers()
  vi.clearAllMocks()
})

describe('PKCE sign-in polling', () => {
  it('stays on the paste step while the session is pending', async () => {
    api.pollOAuthSession.mockResolvedValue({ status: 'pending' })
    await startProviderOAuth(provider, ctx)
    await vi.advanceTimersByTimeAsync(4500)

    expect(api.pollOAuthSession).toHaveBeenCalledWith('antigravity', 's1')
    expect($desktopOnboarding.get().flow.status).toBe('awaiting_user')
  })

  it('leaves the paste step once the backend completes the loopback sign-in', async () => {
    api.pollOAuthSession.mockResolvedValue({ status: 'approved' })
    await startProviderOAuth(provider, ctx)
    await vi.advanceTimersByTimeAsync(2100)

    expect($desktopOnboarding.get().flow.status).not.toBe('awaiting_user')
  })

  it('stops polling when the user submits a pasted code', async () => {
    api.pollOAuthSession.mockResolvedValue({ status: 'pending' })
    api.submitOAuthCode.mockResolvedValue({ message: 'bad code', ok: false, status: 'error' })
    await startProviderOAuth(provider, ctx)
    setOnboardingCode('http://localhost:51121/oauth-callback?code=x')
    await submitOnboardingCode(ctx)
    const pollsAtSubmit = api.pollOAuthSession.mock.calls.length
    await vi.advanceTimersByTimeAsync(6000)

    expect(api.pollOAuthSession.mock.calls.length).toBe(pollsAtSubmit)
    expect($desktopOnboarding.get().flow.status).toBe('error')
  })
})
