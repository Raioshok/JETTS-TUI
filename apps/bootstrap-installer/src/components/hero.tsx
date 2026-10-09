import { type ReactNode } from 'react'

import { cn } from '../lib/utils'

import { BrandMark } from './brand-mark'

interface HeroProps {
  /** Optional status glyph shown on the mark's corner (success / failure). */
  badge?: ReactNode
  title: ReactNode
  children?: ReactNode
  className?: string
}

/**
 * Shared header for the installer's terminal screens: the app tile, a title,
 * and one short line. Each chunk carries a stagger index for the entrance.
 */
export function Hero({ badge, title, children, className }: HeroProps) {
  return (
    <div className={cn('flex w-full max-w-md flex-col items-center text-center', className)}>
      <div className="jt-rise relative" style={{ '--i': 0 } as React.CSSProperties}>
        <BrandMark className="size-16" />
        {badge && <span className="absolute -right-1.5 -bottom-1.5">{badge}</span>}
      </div>
      <h1
        className="jt-rise mt-6 text-[1.75rem] leading-tight font-semibold tracking-tight text-balance text-foreground"
        style={{ '--i': 1 } as React.CSSProperties}
      >
        {title}
      </h1>
      {children && (
        <p
          className="jt-rise mt-2 text-sm leading-relaxed text-pretty text-muted-foreground"
          style={{ '--i': 2 } as React.CSSProperties}
        >
          {children}
        </p>
      )}
    </div>
  )
}
