import { map } from 'nanostores'

// "Is the thread parked at the bottom" is owned by use-stick-to-bottom inside
// ThreadMessageList (the scroll container). That state lives only in that
// subtree, so ThreadMessageList mirrors it into these maps for the composer,
// status stack, and floating jump button — all of which render OUTSIDE the thread.
//
// Everything here is keyed by composer target ('main' | 'tile:<id>'): chats
// open side by side each have their own thread, and one pane scrolling, jumping
// or editing must not dim, scroll or freeze the other.
//
// `$threadScrolledUp` dims the composer / status stack; `$threadJumpButtonVisible`
// shows the floating jump control. Both track `!isAtBottom` today, but stay
// separate so their thresholds can diverge again without touching consumers.
export const $threadScrolledUp = map<Record<string, boolean | undefined>>({})
export const $threadJumpButtonVisible = map<Record<string, boolean | undefined>>({})

export const setThreadAtBottom = (target: string, isAtBottom: boolean) => {
  // Skip no-op writes so subscribers don't churn on every scroll tick.
  if (Boolean($threadScrolledUp.get()[target]) !== !isAtBottom) {
    $threadScrolledUp.setKey(target, !isAtBottom || undefined)
  }

  if (Boolean($threadJumpButtonVisible.get()[target]) !== !isAtBottom) {
    $threadJumpButtonVisible.setKey(target, !isAtBottom || undefined)
  }
}

export const resetThreadScroll = (target: string) => setThreadAtBottom(target, true)

type Handlers = Map<string, Set<() => void>>

function subscribe(handlers: Handlers, target: string, handler: () => void): () => void {
  const set = handlers.get(target) ?? new Set()

  set.add(handler)
  handlers.set(target, set)

  return () => {
    set.delete(handler)

    if (set.size === 0) {
      handlers.delete(target)
    }
  }
}

const fire = (handlers: Handlers, target: string) => handlers.get(target)?.forEach(handler => handler())

// Cross-component bridge: the jump button lives by the composer, the viewport's
// `scrollToBottom` lives inside the thread. The bridge registers a handler; the
// button fires it. Mirrors the composer focus/insert emitter pattern.
const scrollHandlers: Handlers = new Map()

export const onScrollToBottomRequest = (target: string, handler: () => void) =>
  subscribe(scrollHandlers, target, handler)

export const requestScrollToBottom = (target: string) => fire(scrollHandlers, target)

// Inline edit grows a sticky human bubble. Fire on pointerdown so the viewport
// escapes stick-to-bottom before focus/layout; close clears the edit flag when
// the inline composer unmounts.
const editOpenHandlers: Handlers = new Map()
const editCloseHandlers: Handlers = new Map()

export const onThreadEditOpen = (target: string, handler: () => void) => subscribe(editOpenHandlers, target, handler)

export const notifyThreadEditOpen = (target: string) => fire(editOpenHandlers, target)

export const onThreadEditClose = (target: string, handler: () => void) => subscribe(editCloseHandlers, target, handler)

export const notifyThreadEditClose = (target: string) => fire(editCloseHandlers, target)
