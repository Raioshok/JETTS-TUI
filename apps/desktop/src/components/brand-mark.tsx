import { cn } from '@/lib/utils'

// Brand badge: the FreeIDE ◆ prism emblem on a violet tile, identical in
// light/dark. Fills the tile (softly rounded); size via className (default size-14).
export function BrandMark({ className, ...props }: React.ComponentProps<'span'>) {
  return (
    <span
      className={cn(
        'inline-flex size-14 shrink-0 select-none items-center justify-center overflow-hidden rounded-md',
        className
      )}
      style={{
        background: 'linear-gradient(135deg, #cba6f7 0%, #b4befe 100%)',
        color: '#1e1e2e',
      }}
      {...props}
    >
      <span className="font-semibold leading-none" style={{ fontSize: '55%' }}>
        ◆
      </span>
    </span>
  )
}
