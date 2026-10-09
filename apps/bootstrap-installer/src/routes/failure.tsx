import { useStore } from '@nanostores/react'
import { FileText, RefreshCw, X } from 'lucide-react'
import { type CSSProperties } from 'react'

import { Button } from '../components/button'
import { Hero } from '../components/hero'
import {
  $logPath,
  $mode,
  type BootstrapStateModel,
  openLogDir,
  startInstall,
  startUpdate
} from '../store'

interface FailureProps {
  bootstrap: BootstrapStateModel
}

/* Failure screen: what happened, a retry, and the way to the full log. */
export default function Failure({ bootstrap }: FailureProps) {
  const logPath = useStore($logPath)
  const mode = useStore($mode)
  const isUpdate = mode === 'update'

  return (
    <div className="flex h-full flex-col items-center justify-center gap-8 px-10 py-10">
      <Hero
        badge={
          <span className="flex size-6 items-center justify-center rounded-full bg-destructive text-white ring-4 ring-background">
            <X className="size-3.5" strokeWidth={2.5} />
          </span>
        }
        title={isUpdate ? 'The update didn’t finish' : 'Setup didn’t finish'}
      >
        {bootstrap.error ??
          (isUpdate ? 'Something went wrong during the update.' : 'Something went wrong during setup.')}
      </Hero>

      <div className="jt-rise flex flex-col items-center gap-3" style={{ '--i': 3 } as CSSProperties}>
        <div className="flex items-center gap-2">
          <Button className="jt-press rounded-lg" onClick={() => void (isUpdate ? startUpdate() : startInstall())} size="lg">
            <RefreshCw />
            {isUpdate ? 'Retry update' : 'Retry setup'}
          </Button>
          <Button className="jt-press rounded-lg" onClick={() => void openLogDir()} size="lg" variant="outline">
            <FileText />
            Open logs
          </Button>
        </div>

        {logPath && (
          <p className="max-w-md text-center text-xs break-all text-muted-foreground">
            Log: <code className="font-mono">{logPath}</code>
          </p>
        )}
      </div>
    </div>
  )
}
