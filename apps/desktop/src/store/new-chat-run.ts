import { atom } from 'nanostores'

/** Start a fresh chat and send a prompt or slash command — published by the
 *  shell wiring (it owns the session machinery Quick Entry also uses) so pages
 *  like Orchestrator can kick off work from the main pane or a split tile.
 *  (Specs deliberately don't: they run headlessly through `spec.run`.) Null
 *  until wired. */
export const $newChatRunAction = atom<((prompt: string) => void) | null>(null)
