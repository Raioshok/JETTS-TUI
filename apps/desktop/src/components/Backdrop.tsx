import { useStore } from '@nanostores/react'

import { $backdrop } from '@/store/backdrop'

/**
 * Ambient chat backdrop: a soft accent glow above the transcript and a faint
 * dot grid that fades out toward the reading column. Pure CSS, theme-driven,
 * no image decode, nothing repainted while the transcript scrolls.
 */
export function Backdrop() {
  const on = useStore($backdrop)

  if (!on) {
    return null
  }

  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 z-2 overflow-hidden" data-slot="chat-backdrop">
      <div className="absolute inset-x-0 -top-1/3 h-[80%] bg-[radial-gradient(ellipse_55%_50%_at_50%_0%,color-mix(in_srgb,var(--ui-accent)_9%,transparent),transparent_70%)]" />
      <div className="absolute inset-0 bg-[radial-gradient(color-mix(in_srgb,var(--ui-base)_7%,transparent)_1px,transparent_1px)] [background-size:22px_22px] [mask-image:radial-gradient(ellipse_70%_60%_at_50%_35%,#000_10%,transparent_75%)]" />
    </div>
  )
}
