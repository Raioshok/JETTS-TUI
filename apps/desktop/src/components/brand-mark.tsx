import { useId } from 'react'

import { cn } from '@/lib/utils'

/**
 * The JettsTUI prism: a four-facet diamond on an ink tile, identical in light
 * and dark. The tile is the one sanctioned color literal in the app — the mark
 * needs a fixed backdrop to read as the same object everywhere. Size via
 * className (default size-14); the glyph scales with the tile.
 */
export function BrandMark({ className, ...props }: React.ComponentProps<'span'>) {
  return (
    <span
      className={cn(
        'inline-flex size-14 shrink-0 select-none items-center justify-center overflow-hidden rounded-[22%] bg-[#0B0B11] shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]',
        className
      )}
      {...props}
    >
      <PrismGlyph className="size-[68%]" />
    </span>
  )
}

/** The bare prism glyph, for places that supply their own backdrop. */
export function PrismGlyph({ className, ...props }: React.ComponentProps<'svg'>) {
  const id = useId().replace(/:/g, '')
  const lit = `${id}-lit`
  const cool = `${id}-cool`

  return (
    <svg aria-hidden="true" className={className} fill="none" viewBox="0 0 32 32" {...props}>
      <defs>
        <linearGradient gradientUnits="userSpaceOnUse" id={lit} x1="6" x2="16" y1="5" y2="16">
          <stop stopColor="#C9BDFF" />
          <stop offset="1" stopColor="#7357FF" />
        </linearGradient>
        <linearGradient gradientUnits="userSpaceOnUse" id={cool} x1="26" x2="16" y1="16" y2="27">
          <stop stopColor="#5EEAD4" />
          <stop offset="1" stopColor="#3B82F6" />
        </linearGradient>
      </defs>
      <path d="M16 4 5 16h11V4Z" fill={`url(#${lit})`} />
      <path d="M16 4 27 16H16V4Z" fill="#E4DCFF" />
      <path d="M5 16 16 28V16H5Z" fill="#4B2FD6" />
      <path d="M27 16 16 28V16h11Z" fill={`url(#${cool})`} />
      <path d="M16 4 27 16 16 28 5 16 16 4Z" stroke="#fff" strokeOpacity="0.18" strokeWidth="0.75" />
    </svg>
  )
}
