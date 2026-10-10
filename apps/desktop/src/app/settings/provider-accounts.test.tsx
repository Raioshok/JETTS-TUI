import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { OAuthAccount } from '@/types/jettstui'

const api = vi.hoisted(() => ({
  listOAuthAccounts: vi.fn(),
  removeOAuthAccount: vi.fn(),
  switchOAuthAccount: vi.fn()
}))

vi.mock('@/jettstui', async importOriginal => ({
  ...(await importOriginal<object>()),
  ...api
}))

const { ProviderAccounts } = await import('./provider-accounts')

const account = (overrides: Partial<OAuthAccount>): OAuthAccount => ({
  active: false,
  detail: 'oauth',
  exhausted_until: null,
  id: 'a',
  label: 'work@example.com',
  source: 'manual:device_code',
  status: 'ok',
  ...overrides
})

function renderAccounts(accounts: OAuthAccount[], props: { compact?: boolean; onAddAccount?: () => void } = {}) {
  api.listOAuthAccounts.mockResolvedValue({ accounts, provider: 'openai-codex' })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

  return render(
    <QueryClientProvider client={client}>
      <ProviderAccounts providerId="openai-codex" {...props} />
    </QueryClientProvider>
  )
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('ProviderAccounts', () => {
  it('marks the account in use and switches to another with one click', async () => {
    const work = account({ active: true, id: 'w', label: 'work@example.com' })
    const personal = account({ id: 'p', label: 'personal@example.com' })
    renderAccounts([work, personal])
    api.switchOAuthAccount.mockResolvedValue({
      account: { ...personal, active: true },
      ok: true,
      provider: 'openai-codex'
    })

    expect(await screen.findByText('In use')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Use' }))

    await waitFor(() => expect(api.switchOAuthAccount).toHaveBeenCalledWith('openai-codex', 'p'))
    // The list is re-read after a switch so the "In use" badge moves.
    await waitFor(() => expect(api.listOAuthAccounts).toHaveBeenCalledTimes(2))
  })

  it('says when an account is out of quota', async () => {
    renderAccounts([
      account({ active: true, id: 'w' }),
      account({ exhausted_until: Date.now() / 1000 + 3600, id: 'p', label: 'drained@example.com', status: 'exhausted' })
    ])

    expect(await screen.findByText(/out of quota, resets/)).toBeTruthy()
  })

  it('offers adding another account in settings', async () => {
    const onAddAccount = vi.fn()
    renderAccounts([account({ active: true })], { onAddAccount })

    fireEvent.click(await screen.findByRole('button', { name: 'Add account' }))
    expect(onAddAccount).toHaveBeenCalledOnce()
  })

  it('stays hidden in the compact switcher with a single account', async () => {
    renderAccounts([account({ active: true })], { compact: true })

    await waitFor(() => expect(api.listOAuthAccounts).toHaveBeenCalled())
    expect(screen.queryByText('work@example.com')).toBeNull()
  })

  it('links an account Google blocked to its verification page', async () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null)
    renderAccounts([
      account({ active: true, id: 'w' }),
      account({
        exhausted_until: Date.now() / 1000 + 3600,
        id: 'b',
        label: 'blocked@example.com',
        status: 'verify',
        verify_url: 'https://accounts.google.com/verify'
      })
    ])

    expect(await screen.findByText(/needs verification/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Verify' }))
    expect(open).toHaveBeenCalledWith('https://accounts.google.com/verify', '_blank', 'noopener,noreferrer')
  })
})
