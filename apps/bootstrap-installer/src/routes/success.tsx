import { AlertCircle, Check, Loader2 } from 'lucide-react'
import { type CSSProperties, useState } from 'react'

import { Button } from '../components/button'
import { Hero } from '../components/hero'
import { launchJettsTUIDesktop } from '../store'

/*
 * Success screen. Launching the desktop can fail (e.g. Stage-Desktop was
 * skipped and JettsTUI.exe doesn't exist), so the Tauri error is surfaced
 * inline instead of leaving an unresponsive button.
 */
export default function Success() {
  const [error, setError] = useState<string | null>(null)
  const [launching, setLaunching] = useState(false)

  async function handleLaunch() {
    setError(null)
    setLaunching(true)

    try {
      await launchJettsTUIDesktop()
      // On success the installer exits — control never returns here.
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setLaunching(false)
    }
  }

  return (
    <div className="flex h-full flex-col items-center justify-center gap-8 px-10 py-10">
      <Hero
        badge={
          <span className="flex size-6 items-center justify-center rounded-full bg-emerald-500 text-white ring-4 ring-background">
            <Check className="size-3.5" strokeWidth={2.5} />
          </span>
        }
        title="JettsTUI is ready"
      >
        Open it now, or any time from a terminal with{' '}
        <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-foreground">jettstui desktop</code>.
      </Hero>

      <div className="jt-rise flex flex-col items-center gap-3" style={{ '--i': 3 } as CSSProperties}>
        <Button className="jt-press min-w-44 rounded-lg" disabled={launching} onClick={() => void handleLaunch()} size="lg">
          {launching && <Loader2 className="animate-spin" />}
          {launching ? 'Opening…' : 'Open JettsTUI'}
        </Button>

        {error && (
          <div className="flex max-w-md items-start gap-2 text-left text-sm" role="alert">
            <AlertCircle className="mt-0.5 shrink-0 text-destructive" size={16} />
            <div className="min-w-0">
              <div className="font-medium text-destructive">Couldn&rsquo;t open the desktop app</div>
              <div className="mt-0.5 text-muted-foreground">{error}</div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
