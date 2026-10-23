import * as React from 'react'

import { Codicon } from '@/components/ui/codicon'
import { cn } from '@/lib/utils'

/** Inset stroke for a vertical tab rail — content-facing edge. */
export const PANE_TAB_STRIP_LINE_LEFT = 'shadow-[inset_1px_0_0_var(--ui-stroke-tertiary)]'
export const PANE_TAB_STRIP_LINE_RIGHT = 'shadow-[inset_-1px_0_0_var(--ui-stroke-tertiary)]'

const TAB =
  'group/tab relative flex shrink-0 items-center text-[0.6875rem] font-medium transition-colors select-none [-webkit-app-region:no-drag]'

const TAB_HORIZONTAL = 'h-[1.5rem] min-w-0 max-w-52 rounded-md px-1.5'

const TAB_VERTICAL =
  'w-full max-h-48 justify-center not-first:border-t not-first:border-t-(--ui-stroke-quaternary) [writing-mode:vertical-rl]'

const TAB_ACTIVE =
  'bg-background text-foreground border border-(--ui-stroke-secondary) shadow-xs [--tab-bg:var(--pane-tab-active-bg,var(--ui-editor-surface-background))]'

const TAB_ACTIVE_UNDERLINE = ''

const TAB_IDLE =
  'border border-transparent bg-transparent text-(--ui-text-tertiary) hover:bg-(--ui-control-hover-background) hover:text-(--ui-text-primary)'

interface PaneTabProps extends React.ComponentProps<'div'> {
  active?: boolean
  dirty?: boolean
  /** Close gesture, no hover X (too easy to hit on small tabs): middle-click,
   *  or ⌘-click as the trackpad-friendly Mac equivalent. */
  onClose?: () => void
  /** Vertical rail form (collapsed sidebar zones). */
  vertical?: boolean
  /** Content-facing edge of a vertical rail — the strip line the active tab cuts. */
  side?: 'left' | 'right'
}

/** ⌘-click (metaKey + primary button) — the Mac has no middle button, so this
 *  is the trackpad equivalent of middle-click-to-close. Guarded on metaKey so
 *  it never collides with left-click (activate/drag) or ⌃-click (macOS context
 *  menu). */
const isMetaClose = (event: { button: number; metaKey: boolean }) => event.button === 0 && event.metaKey

/**
 * Editor tab shell — preview rail + zone headers + collapsed vertical rails.
 *
 * Defaults need no vars: the active tab takes the editor surface, inactive the
 * sidebar one. Override `--pane-tab-active-bg` to change what the active tab
 * merges into, `--pane-tab-strip-bg` for a gutter unlike the bar around it.
 */
export const PaneTab = React.forwardRef<HTMLDivElement, PaneTabProps>(function PaneTab(
  {
    active = false,
    dirty = false,
    onClose,
    onAuxClick,
    onMouseDown,
    onPointerDown,
    onClickCapture,
    vertical = false,
    side = 'left',
    children,
    className,
    ...props
  },
  ref
) {
  // Vertical rails only. Horizontal tabs draw no bottom border — the strip owns
  // that rule, and a per-tab border stacked a second translucent line over it.
  const edge = vertical ? (side === 'right' ? 'border-l' : 'border-r') : undefined

  return (
    <div
      className={cn(
        TAB,
        vertical ? TAB_VERTICAL : TAB_HORIZONTAL,
        edge,
        active
          ? cn(TAB_ACTIVE, !vertical && TAB_ACTIVE_UNDERLINE)
          : cn(TAB_IDLE, edge && `${edge}-(--ui-stroke-tertiary)`),
        className
      )}
      data-active={active}
      data-pane-tab=""
      data-vertical={vertical || undefined}
      onAuxClick={event => {
        // Middle-click closes (browser/IDE). Swallow mousedown so Chromium
        // doesn't autoscroll.
        if (onClose && event.button === 1) {
          event.preventDefault()
          onClose()
        }

        onAuxClick?.(event)
      }}
      onClickCapture={event => {
        // Sites whose tab activates on the label's own onClick (the preview
        // rail) fire it AFTER our pointerdown close — swallow that stray click
        // in the capture phase so it can't re-select the just-closed tab.
        if (onClose && isMetaClose(event)) {
          event.preventDefault()
          event.stopPropagation()
        }

        onClickCapture?.(event)
      }}
      onMouseDown={event => {
        if (onClose && event.button === 1) {
          event.preventDefault()
        }

        onMouseDown?.(event)
      }}
      onPointerDown={event => {
        // ⌘-click closes. Preempt here — the tab strips activate/drag on
        // pointerdown (drag-session onTap), so we must claim the press before
        // the shell's own handler starts a drag, and skip it entirely.
        if (onClose && isMetaClose(event)) {
          event.preventDefault()
          event.stopPropagation()
          onClose()

          return
        }

        onPointerDown?.(event)
      }}
      ref={ref}
      {...props}
    >
      {children}
      {onClose && !vertical && (
        <button
          aria-label="Close tab"
          className={cn(
            'mr-1 flex size-3.5 shrink-0 items-center justify-center rounded-[3px] text-(--ui-text-quaternary) transition-opacity hover:bg-(--ui-control-hover-background) hover:text-foreground',
            active ? 'opacity-70 hover:opacity-100' : 'opacity-0 group-hover/tab:opacity-70 hover:opacity-100!'
          )}
          onClick={event => {
            event.preventDefault()
            event.stopPropagation()
            onClose()
          }}
          onPointerDown={event => {
            event.stopPropagation()
          }}
          type="button"
        >
          <Codicon name="close" size="0.625rem" />
        </button>
      )}
      {dirty && (
        <span
          aria-hidden
          className={cn(
            'pointer-events-none absolute grid size-4 place-items-center',
            vertical ? 'bottom-1.5 left-1/2 -translate-x-1/2' : 'right-1.5 top-1/2 -translate-y-1/2'
          )}
        >
          <span className="size-2 rounded-full bg-amber-500 shadow-[0_0_0_2px_var(--tab-bg),0_1px_2px_rgba(0,0,0,0.45)] dark:bg-amber-400" />
        </span>
      )}
    </div>
  )
})

interface PaneTabLabelProps extends React.ComponentProps<'button'> {
  /** `button` when the label is the activation target (preview rail);
   *  default `span` defers to the shell (zone drag/activate). */
  as?: 'button' | 'span'
}

/** Truncating label inside a `PaneTab`. `className` merges into the text span
 *  (e.g. `normal-case tracking-normal` for filenames). */
export const PaneTabLabel = React.forwardRef<HTMLElement, PaneTabLabelProps>(function PaneTabLabel(
  { as = 'span', className, children, ...props },
  ref
) {
  const Comp = as as React.ElementType

  return (
    <Comp
      className="flex h-full min-w-0 max-w-full items-center overflow-hidden px-1 text-left outline-none group-data-[vertical]/tab:h-auto group-data-[vertical]/tab:w-full group-data-[vertical]/tab:justify-center group-data-[vertical]/tab:py-1.5"
      ref={ref}
      {...props}
    >
      <span className={cn('block min-w-0 truncate text-[0.72rem] font-medium tracking-normal', className)}>
        {children}
      </span>
    </Comp>
  )
})
