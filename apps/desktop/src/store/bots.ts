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
  /** Live state of the bot's thread: waiting on an approval, mid-task, or free. */
  status?: JettsBotStatus
  /** A teach-by-showing lesson is recording (or waiting for Stop & learn). */
  watching?: boolean
  /** Only these tools (enforced at dispatch); absent = every tool. */
  tools?: null | string[]
  /** Tools that always need the user's OK in this Bot's chats. */
  ask_before?: null | string[]
  /** Spend of the Bot's thread (USD) — all time and over the last 7 days. */
  usage?: { cost_usd: number; cost_usd_week: number; tokens: number }
}

/** "$1.20", or "<$0.01" for spend too small to round to a cent. */
export function formatBotCost(usd: number): string {
  return usd > 0 && usd < 0.005 ? '<$0.01' : `$${usd.toFixed(2)}`
}

export const JETTS_BOT_STATUSES = ['idle', 'working', 'needs_you'] as const

export type JettsBotStatus = (typeof JETTS_BOT_STATUSES)[number]

/** Bots whose status just moved to a state the user should hear about. */
export function botsNeedingNotice(
  previous: ReadonlyMap<string, JettsBotStatus>,
  bots: readonly JettsBot[]
): { bot: JettsBot; status: 'idle' | 'needs_you' }[] {
  return bots.flatMap<{ bot: JettsBot; status: 'idle' | 'needs_you' }>(bot => {
    const was = previous.get(bot.id)
    const now = bot.status ?? 'idle'

    if (now === 'needs_you' && was !== 'needs_you') {
      return [{ bot, status: 'needs_you' }]
    }

    return now === 'idle' && (was === 'working' || was === 'needs_you') ? [{ bot, status: 'idle' }] : []
  })
}

/** One-shot: the next new chat is created as this bot's thread (see session.create `bot`). */
export const $newChatBot = atom<null | Pick<JettsBot, 'id' | 'name'>>(null)

/** The Jetts Bot the foreground chat is with ('' for an ordinary chat), from session.info. */
export const $currentBotName = atom('')
