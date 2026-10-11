import { atom } from 'nanostores'

/** Start a fresh chat and send a prompt — published by the shell wiring (it
 *  owns the session machinery Quick Entry also uses) so the Orchestrator page
 *  can run a task from the main pane or a split tile. Null until wired. */
export const $orchestratorRunAction = atom<((prompt: string) => void) | null>(null)
