import type { Icon, IconProps } from '@tabler/icons-react'
import { forwardRef } from 'react'

import { JETTS_GLYPHS } from '@/components/ui/jetts-glyphs'
import { cn } from '@/lib/utils'

/**
 * A JettsTUI glyph as a drop-in for a Tabler icon: same props (`size`,
 * `stroke`, `color`, `title`, any svg attr) and the same `tabler-icon` class, so
 * call sites and size utilities keep working. `filled` paints the shape too —
 * the stand-in for Tabler's `*Filled` variants.
 */
export function jettsIcon(glyph: string, { filled = false } = {}): Icon {
  const d = JETTS_GLYPHS[glyph]

  if (!d) {
    throw new Error(`jettsIcon: no glyph named "${glyph}"`)
  }

  const JettsIcon = forwardRef<SVGSVGElement, IconProps>(
    ({ children, className, color = 'currentColor', size = 24, stroke = 1.75, title, ...rest }, ref) => (
      <svg
        className={cn('tabler-icon', `jetts-icon-${glyph}`, className)}
        fill={filled ? color : 'none'}
        height={size}
        ref={ref}
        stroke={color}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={stroke}
        viewBox="0 0 24 24"
        width={size}
        xmlns="http://www.w3.org/2000/svg"
        {...rest}
      >
        {title ? <title>{title}</title> : null}
        <path d={d} />
        {children}
      </svg>
    )
  )

  JettsIcon.displayName = `JettsIcon(${glyph}${filled ? ', filled' : ''})`

  return JettsIcon as Icon
}
