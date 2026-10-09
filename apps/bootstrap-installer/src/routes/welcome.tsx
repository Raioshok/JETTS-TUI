import { Bot, GitBranch, Package } from 'lucide-react'
import { type CSSProperties } from 'react'

import { Button } from '../components/button'
import { Hero } from '../components/hero'
import { startInstall } from '../store'

const STEPS = [
  { icon: Package, title: 'Runtime', detail: 'Python, uv, and the command-line tools' },
  { icon: GitBranch, title: 'Git', detail: 'Used for updates and the agent’s terminal' },
  { icon: Bot, title: 'JettsTUI', detail: 'The agent, its skills, and the desktop app' }
]

/*
 * Welcome screen. No install-path picker: the default location is right for
 * almost everyone, and the CLI installer covers custom homes.
 */
export default function Welcome() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-8 px-10 py-10">
      <Hero title="Set up JettsTUI">
        A one-time setup that runs in the background and takes a few minutes.
      </Hero>

      <ul className="jt-rise w-full max-w-md overflow-hidden rounded-xl border border-border bg-card" style={{ '--i': 3 } as CSSProperties}>
        {STEPS.map(({ icon: Icon, title, detail }) => (
          <li className="flex items-center gap-3 px-4 py-3 [&+&]:border-t [&+&]:border-border" key={title}>
            <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Icon className="size-4" strokeWidth={1.75} />
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-medium text-foreground">{title}</span>
              <span className="block text-xs text-muted-foreground">{detail}</span>
            </span>
          </li>
        ))}
      </ul>

      <div className="jt-rise flex flex-col items-center gap-2" style={{ '--i': 4 } as CSSProperties}>
        <Button className="jt-press min-w-44 rounded-lg" onClick={() => void startInstall()} size="lg">
          Install JettsTUI
        </Button>
        <span className="text-xs text-muted-foreground">You can keep using your computer while it runs.</span>
      </div>
    </div>
  )
}
