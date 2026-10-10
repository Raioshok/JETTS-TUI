import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ProviderQuotaResponse } from '@/jettstui'

const api = vi.hoisted(() => ({ getProviderQuotas: vi.fn() }))

vi.mock('@/jettstui', async importOriginal => ({
  ...(await importOriginal<object>()),
  ...api
}))

const { ProviderQuotaSection } = await import('./provider-quota')

function renderWith(response: ProviderQuotaResponse) {
  api.getProviderQuotas.mockResolvedValue(response)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

  return render(
    <QueryClientProvider client={client}>
      <ProviderQuotaSection />
    </QueryClientProvider>
  )
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('ProviderQuotaSection', () => {
  it('shows each quota window with its used share and plan', async () => {
    renderWith({
      providers: [
        {
          id: 'antigravity',
          name: 'Google Antigravity',
          plan: 'Google AI Ultra',
          supported: true,
          windows: [{ detail: null, label: 'Gemini 3 Pro (High)', reset_at: null, used_percent: 92.4 }]
        }
      ]
    })

    expect(await screen.findByText('Gemini 3 Pro (High)')).toBeTruthy()
    expect(screen.getByText('Google AI Ultra')).toBeTruthy()
    expect(screen.getByText('92% used')).toBeTruthy()
    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('92')
  })

  it('says when a signed-in provider does not report quota', async () => {
    renderWith({ providers: [{ id: 'xai-oauth', name: 'xAI Grok', supported: false }] })

    expect(await screen.findByText("This provider doesn't report quota.")).toBeTruthy()
    expect(screen.queryByRole('progressbar')).toBeNull()
  })

  it('explains how to get quota when no subscription provider is signed in', async () => {
    renderWith({ providers: [] })

    expect(await screen.findByText(/Sign in to a subscription provider/)).toBeTruthy()
  })
})
