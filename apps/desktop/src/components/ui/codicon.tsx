import type { Icon } from '@tabler/icons-react'
import type * as React from 'react'

import { cn } from '@/lib/utils'

import { JETTS_GLYPHS } from './jetts-glyphs'

export interface CodiconProps extends React.HTMLAttributes<HTMLElement> {
  name: string
  size?: number | string
  spinning?: boolean
}

export function Codicon({ className, name, size, spinning, style, ...props }: CodiconProps) {
  const glyph = JETTS_GLYPHS[name]

  // Our own glyph when we have one. Keeps every codicon class so selectors still
  // match; styles.css hides the font's ::before glyph for [data-glyph].
  if (glyph) {
    return (
      <i
        aria-hidden="true"
        className={cn('codicon', `codicon-${name}`, spinning && 'codicon-modifier-spin', className)}
        data-glyph={name}
        style={{ fontSize: size, ...style }}
        {...props}
      >
        <svg
          fill="none"
          height="1em"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.75}
          viewBox="0 0 24 24"
          width="1em"
        >
          <path d={glyph} />
        </svg>
      </i>
    )
  }

  return (
    <i
      aria-hidden="true"
      className={cn('codicon', `codicon-${name}`, spinning && 'codicon-modifier-spin', className)}
      style={{ fontSize: size, ...style }}
      {...props}
    />
  )
}

/** Wrap a codicon as a Tabler-shaped icon for nav rows that expect `IconComponent`. */
export function codiconIcon(name: string): Icon {
  function CodiconIcon({ className }: { className?: string }) {
    return <Codicon aria-hidden className={cn('leading-none', className)} name={name} size="1em" />
  }

  CodiconIcon.displayName = `Codicon(${name})`

  return CodiconIcon as Icon
}
