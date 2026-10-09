import { cn } from '../lib/utils'

import { PrismMark } from './prism-mark'

/** JettsTUI app tile: the prism mark on the ink tile of the desktop icon. */
export function BrandMark({ className, ...props }: React.ComponentProps<'span'>) {
  return (
    <span
      className={cn(
        'inline-flex size-14 shrink-0 select-none items-center justify-center rounded-[22%] bg-[#13121c]',
        'shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08),0_8px_24px_-8px_rgb(115_87_255/0.45)]',
        className
      )}
      {...props}
    >
      <PrismMark className="size-[58%]" />
    </span>
  )
}
