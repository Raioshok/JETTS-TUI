import { cn } from '../lib/utils'

// JettsTUI badge, using the teal-on-ink palette of the desktop mark.
export function BrandMark({ className, ...props }: React.ComponentProps<'span'>) {
  return (
    <span
      className={cn('inline-flex size-14 shrink-0 select-none items-center justify-center overflow-hidden rounded-md', className)}
      style={{ background: '#101b1d', color: '#54d6b1' }}
      {...props}
    >
      <span className="font-semibold leading-none" style={{ fontSize: '55%' }}>◆</span>
    </span>
  )
}
