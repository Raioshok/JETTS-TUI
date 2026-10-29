import { atom } from 'nanostores'

/** A Jetts Bot as `bots.list` returns it (agent/bots.py owns the truth). */
export interface JettsBot {
  id: string
  model?: null | string
  name: string
  provider?: null | string
  role: string
  /** The bot's ongoing conversation; absent until its first chat. */
  session_id?: null | string
}

/** One-shot: the next new chat is created as this bot's thread (see session.create `bot`). */
export const $newChatBot = atom<null | string>(null)
