/**
 * Dedicated "Sign in with Claude" card for the Providers > Accounts tab.
 *
 * Wraps the existing PKCE OAuth flow (startOAuthLogin / submitOAuthCode /
 * pollOAuthSession) in a self-contained inline UI so users don't need the
 * full first-run onboarding overlay just to connect their Claude subscription.
 *
 * The Anthropic PKCE flow has two shapes:
 *  - loopback=true  → JettsTUI listens on port 51121; auto-completes on the
 *                     server callback. We poll every POLL_MS until approved.
 *  - loopback=false → Port 51121 is busy; user must paste the auth code.
 *
 * Either way the user's browser opens claude.ai to authorize, then returns
 * an `<code>#<state>` string that we exchange for tokens via submitOAuthCode.
 */

import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import { useI18n } from '@/i18n'
import { Check, ChevronRight, ExternalLink, Loader2, LogIn, Trash2, X } from '@/lib/icons'
import {
  cancelOAuthSession,
  disconnectOAuthProvider,
  pollOAuthSession,
  startOAuthLogin,
  submitOAuthCode
} from '@/jettstui'
import { notifyError } from '@/store/notifications'
import type { OAuthProvider } from '@/types/jettstui'

/** How often to poll the session status when loopback=true. */
const POLL_MS = 2_000
const PROVIDER_ID = 'anthropic'

type FlowStage =
  | { stage: 'idle' }
  | { stage: 'starting' }
  | { stage: 'awaiting_code'; sessionId: string; authUrl: string; loopback: boolean }
  | { stage: 'submitting'; sessionId: string; authUrl: string }
  | { stage: 'error'; message: string; authUrl?: string; sessionId?: string }

interface ClaudeOAuthLoginProps {
  /** Current status of the anthropic provider, from the parent's query. */
  provider: OAuthProvider
  /** Called after a successful sign-in so the parent refreshes the list. */
  onRefresh: () => void
}

export function ClaudeOAuthLogin({ onRefresh, provider }: ClaudeOAuthLoginProps) {
  const { t } = useI18n()
  const copy = t.settings.claudeOAuth
  const queryClient = useQueryClient()
  const loggedIn = provider.status?.logged_in
  const [flow, setFlow] = useState<FlowStage>({ stage: 'idle' })
  const [code, setCode] = useState('')
  const [disconnecting, setDisconnecting] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const codeRef = useRef<HTMLInputElement | null>(null)

  // Clean up poll timer on unmount.
  useEffect(() => {
    return () => {
      if (pollRef.current !== null) {
        clearInterval(pollRef.current)
      }
    }
  }, [])

  async function handleSignIn() {
    setFlow({ stage: 'starting' })
    setCode('')
    try {
      const start = await startOAuthLogin(PROVIDER_ID)
      if (start.flow !== 'pkce') {
        setFlow({ stage: 'error', message: `Unexpected flow: ${start.flow}` })
        return
      }
      const { auth_url: authUrl, session_id: sessionId, loopback = false } = start
      window.open(authUrl, '_blank', 'noopener,noreferrer')
      setFlow({ stage: 'awaiting_code', sessionId, authUrl, loopback })

      if (loopback) {
        // Auto-complete: poll until server receives the callback.
        pollRef.current = setInterval(() => void pollSession(sessionId, authUrl), POLL_MS)
      } else {
        // Focus the paste box once it renders.
        setTimeout(() => codeRef.current?.focus(), 50)
      }
    } catch (err) {
      setFlow({ stage: 'error', message: err instanceof Error ? err.message : String(err) })
    }
  }

  async function pollSession(sessionId: string, authUrl: string) {
    try {
      const { status, error_message } = await pollOAuthSession(PROVIDER_ID, sessionId)
      if (status === 'approved') {
        clearPollTimer()
        handleSuccess()
      } else if (status !== 'pending') {
        clearPollTimer()
        setFlow({ stage: 'error', message: error_message ?? status, authUrl, sessionId })
      }
    } catch {
      // Transient — keep polling.
    }
  }

  async function handleSubmitCode() {
    if (flow.stage !== 'awaiting_code') {
      return
    }
    const { sessionId, authUrl } = flow
    setFlow({ stage: 'submitting', sessionId, authUrl })
    try {
      const resp = await submitOAuthCode(PROVIDER_ID, sessionId, code.trim())
      if (resp.ok) {
        handleSuccess()
      } else {
        setFlow({
          stage: 'error',
          message: resp.message ?? 'Authorization rejected.',
          authUrl,
          sessionId
        })
      }
    } catch (err) {
      setFlow({
        stage: 'error',
        message: err instanceof Error ? err.message : String(err),
        authUrl,
        sessionId
      })
    }
  }

  function handleSuccess() {
    setFlow({ stage: 'idle' })
    setCode('')
    void queryClient.invalidateQueries({ queryKey: ['oauth-providers'] })
    onRefresh()
  }

  function clearPollTimer() {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  function handleCancel() {
    clearPollTimer()
    const sessionId =
      flow.stage === 'awaiting_code' || flow.stage === 'submitting' || flow.stage === 'error'
        ? flow.sessionId
        : undefined
    if (sessionId) {
      cancelOAuthSession(sessionId).catch(() => undefined)
    }
    setFlow({ stage: 'idle' })
    setCode('')
  }

  async function handleSignOut() {
    if (!window.confirm(copy.signOutConfirm)) {
      return
    }
    setDisconnecting(true)
    try {
      await disconnectOAuthProvider(PROVIDER_ID)
      void queryClient.invalidateQueries({ queryKey: ['oauth-providers'] })
      onRefresh()
    } catch (err) {
      notifyError(err, copy.signOutFailed)
    } finally {
      setDisconnecting(false)
    }
  }

  if (loggedIn) {
    return <SignedInCard provider={provider} disconnecting={disconnecting} onSignOut={() => void handleSignOut()} />
  }

  if (flow.stage === 'starting') {
    return (
      <div className="flex items-center gap-2 rounded-[8px] border border-(--ui-border) bg-(--ui-card-background) px-4 py-3 text-[length:var(--conversation-caption-font-size)] text-muted-foreground">
        <Loader2 className="size-3.5 animate-spin" />
        {copy.opening}
      </div>
    )
  }

  if (flow.stage === 'awaiting_code' || flow.stage === 'submitting') {
    const busy = flow.stage === 'submitting'
    const loopback = flow.stage === 'awaiting_code' ? flow.loopback : false
    return (
      <div className="grid gap-2 rounded-[8px] border border-(--ui-border) bg-(--ui-card-background) px-4 py-3">
        <div className="flex items-start justify-between gap-2">
          <p className="text-[length:var(--conversation-caption-font-size)] leading-relaxed text-muted-foreground">
            {loopback ? copy.loopbackHint : copy.pasteCodeHint}
          </p>
          <button
            aria-label={t.common.cancel}
            className="mt-0.5 shrink-0 text-muted-foreground/60 transition hover:text-muted-foreground"
            onClick={handleCancel}
            type="button"
          >
            <X className="size-3.5" />
          </button>
        </div>

        {loopback ? (
          <div className="flex items-center gap-2 text-[length:var(--conversation-caption-font-size)] text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" />
            {copy.waitingAuthorize}
          </div>
        ) : (
          <div className="flex gap-2">
            <input
              aria-label={copy.pasteCode}
              className="min-w-0 flex-1 rounded-[6px] border border-(--ui-border) bg-(--ui-input-background) px-2.5 py-1.5 text-[length:var(--conversation-caption-font-size)] font-mono outline-none placeholder:text-muted-foreground/60 focus:ring-1 focus:ring-(--ui-ring)"
              disabled={busy}
              onChange={e => setCode(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter') {
                  void handleSubmitCode()
                }
              }}
              placeholder={copy.pasteCode}
              ref={codeRef}
              type="text"
              value={code}
            />
            <Button
              disabled={busy || code.trim().length === 0}
              onClick={() => void handleSubmitCode()}
              size="sm"
              type="button"
            >
              {busy ? <Loader2 className="size-3.5 animate-spin" /> : null}
              {busy ? copy.submitting : t.onboarding.signedIn}
            </Button>
          </div>
        )}

        <a
          className="inline-flex items-center gap-1 text-[length:var(--conversation-caption-font-size)] text-primary/80 hover:text-primary"
          href={flow.stage === 'awaiting_code' ? flow.authUrl : undefined}
          onClick={e => {
            e.preventDefault()
            window.open(
              flow.stage === 'awaiting_code' ? flow.authUrl : '',
              '_blank',
              'noopener,noreferrer'
            )
          }}
          rel="noopener noreferrer"
          target="_blank"
        >
          <ExternalLink className="size-3" />
          {copy.reopenBrowser}
        </a>
      </div>
    )
  }

  if (flow.stage === 'error') {
    const { message, authUrl, sessionId } = flow
    return (
      <div className="grid gap-2 rounded-[8px] border border-destructive/30 bg-destructive/5 px-4 py-3">
        <p className="text-[length:var(--conversation-caption-font-size)] text-destructive">{message}</p>
        <div className="flex gap-2">
          <Button onClick={() => void handleSignIn()} size="sm" type="button" variant="outline">
            {t.onboarding.tryAgain}
          </Button>
          <Button
            onClick={() => {
              if (sessionId) {
                cancelOAuthSession(sessionId).catch(() => undefined)
              }
              setFlow({ stage: 'idle' })
            }}
            size="sm"
            type="button"
            variant="ghost"
          >
            {t.common.cancel}
          </Button>
        </div>
        {authUrl && (
          <a
            className="inline-flex items-center gap-1 text-[length:var(--conversation-caption-font-size)] text-primary/80 hover:text-primary"
            href={authUrl}
            onClick={e => {
              e.preventDefault()
              window.open(authUrl, '_blank', 'noopener,noreferrer')
            }}
            rel="noopener noreferrer"
            target="_blank"
          >
            <ExternalLink className="size-3" />
            {copy.reopenBrowser}
          </a>
        )}
      </div>
    )
  }

  // idle — not signed in
  return (
    <div className="grid gap-2 rounded-[8px] border border-(--ui-border) bg-(--ui-card-background) px-4 py-3">
      <div>
        <p className="text-[length:var(--conversation-text-font-size)] font-semibold">{copy.title}</p>
        <p className="mt-0.5 text-[length:var(--conversation-caption-font-size)] leading-relaxed text-muted-foreground">
          {copy.description}
        </p>
      </div>
      <div>
        <Button onClick={() => void handleSignIn()} size="sm" type="button">
          <LogIn className="size-3.5" />
          {copy.signIn}
        </Button>
      </div>
    </div>
  )
}

function SignedInCard({
  disconnecting,
  onSignOut,
  provider
}: {
  disconnecting: boolean
  onSignOut: () => void
  provider: OAuthProvider
}) {
  const { t } = useI18n()
  const copy = t.settings.claudeOAuth
  const label = provider.status?.source_label ?? provider.name

  return (
    <div className="grid gap-1.5 rounded-[8px] border border-(--ui-border) bg-(--ui-card-background) px-4 py-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-1.5">
            <p className="text-[length:var(--conversation-text-font-size)] font-semibold">{copy.title}</p>
            <span className="inline-flex items-center gap-1 bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
              <Check className="size-3" />
              {t.onboarding.connected}
            </span>
          </div>
          <p className="mt-0.5 text-[length:var(--conversation-caption-font-size)] text-muted-foreground">
            {copy.signedInVia(label)}
          </p>
          {provider.status?.expires_at && (
            <p className="mt-0.5 text-[0.68rem] text-muted-foreground/70">
              {copy.expiresAt(new Date(provider.status.expires_at).toLocaleDateString())}
            </p>
          )}
        </div>
        <Button
          aria-label={copy.signOut}
          disabled={disconnecting}
          onClick={onSignOut}
          size="icon-xs"
          title={copy.signOut}
          type="button"
          variant="ghost"
        >
          {disconnecting ? <Loader2 className="size-3.5 animate-spin" /> : <Trash2 className="size-3.5" />}
        </Button>
      </div>
    </div>
  )
}
