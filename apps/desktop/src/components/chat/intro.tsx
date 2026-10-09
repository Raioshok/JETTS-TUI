import { useGSAP } from '@gsap/react'
import { useStore } from '@nanostores/react'
import gsap from 'gsap'
import { useRef, useState } from 'react'

import { BrandMark } from '@/components/brand-mark'
import { KbdCombo } from '@/components/ui/kbd'
import { useI18n } from '@/i18n'
import { capitalize, normalize } from '@/lib/text'
import { $bindings } from '@/store/keybinds'

import introCopyJsonl from './intro-copy.jsonl?raw'

type IntroCopy = {
  headline: string
  body: string
}

type IntroCopyRecord = IntroCopy & {
  personality: string
}

export type IntroProps = {
  personality?: string
  seed?: number
}

const NEUTRAL_PERSONALITIES = new Set(['', 'default', 'none', 'neutral'])

const FALLBACK_COPY: IntroCopy[] = [
  {
    headline: 'What are we moving today?',
    body: "Send a bug, branch, plan, or rough idea. I'll inspect the repo and turn it into the next concrete step."
  },
  {
    headline: "What's on your mind?",
    body: "Bring the code, question, or stuck part. I'll read the room before making changes."
  },
  {
    headline: 'What should JettsTUI look at?',
    body: "Send the task, failing path, or half-formed plan. I'll help turn it into action."
  },
  {
    headline: 'Where should we start?',
    body: "Bring the problem, goal, or file. I'll inspect first and keep the next step concrete."
  },
  {
    headline: 'What needs attention?',
    body: "Send the context you have. I'll help sort it into a plan or a fix."
  }
]

function normalizeKey(value?: string): string {
  return normalize(value)
}

function titleize(value: string): string {
  return value
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map(capitalize)
    .join(' ')
}

function isIntroCopyRecord(value: unknown): value is IntroCopyRecord {
  if (!value || typeof value !== 'object') {
    return false
  }

  const record = value as Record<string, unknown>

  return (
    typeof record.personality === 'string' &&
    typeof record.headline === 'string' &&
    typeof record.body === 'string' &&
    Boolean(record.personality.trim()) &&
    Boolean(record.headline.trim()) &&
    Boolean(record.body.trim())
  )
}

function parseIntroCopy(raw: string): Record<string, IntroCopy[]> {
  const byPersonality: Record<string, IntroCopy[]> = {}

  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim()

    if (!trimmed) {
      continue
    }

    try {
      const parsed: unknown = JSON.parse(trimmed)

      if (!isIntroCopyRecord(parsed)) {
        continue
      }

      const key = normalizeKey(parsed.personality)
      byPersonality[key] ??= []
      byPersonality[key].push({
        headline: parsed.headline.trim(),
        body: parsed.body.trim()
      })
    } catch {
      // Bad generated copy should not break the whole desktop app.
    }
  }

  return byPersonality
}

const INTRO_COPY_BY_PERSONALITY = parseIntroCopy(introCopyJsonl)

function neutralCopy(): IntroCopy[] {
  return INTRO_COPY_BY_PERSONALITY.none || INTRO_COPY_BY_PERSONALITY.default || FALLBACK_COPY
}

function fallbackCopyForPersonality(personalityKey: string): IntroCopy[] {
  if (NEUTRAL_PERSONALITIES.has(personalityKey)) {
    return neutralCopy()
  }

  const label = titleize(personalityKey)

  return [
    {
      headline: `${label} mode is on. What should we work on?`,
      body: "Send the task, file, or rough idea. I'll use your configured voice and keep the work grounded in this repo."
    },
    {
      headline: `What does ${label} JettsTUI need to see?`,
      body: "Bring the context or the stuck part. I'll adapt to your configured personality."
    },
    {
      headline: `${label} mode is ready.`,
      body: "Send the problem, file, or idea. I'll follow the personality you've configured."
    },
    {
      headline: `What should ${label} JettsTUI tackle?`,
      body: "Drop the task here. I'll keep the work grounded in the repo."
    },
    {
      headline: 'Where should we begin?',
      body: `Give me the context and I'll answer in ${label} mode.`
    }
  ]
}

function pickCopy(copies: IntroCopy[], seed = 0): IntroCopy {
  return copies[Math.abs(seed) % copies.length] || FALLBACK_COPY[0]
}

function resolveCopy(personality?: string, seed?: number): IntroCopy {
  const personalityKey = normalizeKey(personality)

  const copies = NEUTRAL_PERSONALITIES.has(personalityKey)
    ? INTRO_COPY_BY_PERSONALITY[personalityKey] || neutralCopy()
    : INTRO_COPY_BY_PERSONALITY[personalityKey] || fallbackCopyForPersonality(personalityKey)

  return pickCopy(copies, seed)
}

gsap.registerPlugin(useGSAP)

// Shortcuts worth teaching on an empty session. Labels reuse the keybind panel
// copy, combos read live from the user's bindings, unbound actions drop out.
const HINT_ACTIONS = ['nav.commandPalette', 'nav.skills', 'keybinds.openPanel'] as const

function IntroHints() {
  const { t } = useI18n()
  const bindings = useStore($bindings)

  const hints = HINT_ACTIONS.flatMap(id => {
    const combo = bindings[id]?.[0]

    return combo ? [{ combo, id, label: t.keybinds.actions[id] }] : []
  })

  if (!hints.length) {
    return null
  }

  return (
    <ul className="m-0 flex list-none flex-wrap items-center justify-center gap-x-5 gap-y-2 p-0" data-intro-stagger>
      {hints.map(hint => (
        <li className="flex items-center gap-2 text-[0.75rem] text-(--ui-text-tertiary)" key={hint.id}>
          <KbdCombo combo={hint.combo} size="sm" />
          <span>{hint.label}</span>
        </li>
      ))}
    </ul>
  )
}

export function Intro({ personality, seed }: IntroProps) {
  const [mountSeed] = useState(() => Math.floor(Math.random() * 100000))
  const copy = resolveCopy(personality, mountSeed + (seed ?? 0))
  const scope = useRef<HTMLDivElement>(null)

  // One staged entrance per empty session: an infrequent moment where the
  // sequence (mark → headline → body → hints) communicates hierarchy.
  useGSAP(
    () => {
      // No matchMedia (jsdom, some embedders) → render the final state, static.
      if (typeof window.matchMedia !== 'function') {
        return
      }

      const mm = gsap.matchMedia()

      mm.add('(prefers-reduced-motion: no-preference)', () => {
        gsap.from('[data-intro-stagger]', {
          autoAlpha: 0,
          y: 10,
          filter: 'blur(4px)',
          duration: 0.55,
          ease: 'power3.out',
          stagger: 0.08,
          clearProps: 'filter,transform'
        })
        gsap.from('[data-intro-halo]', { autoAlpha: 0, scale: 0.6, duration: 1.1, ease: 'power2.out' })
      })

      return () => mm.revert()
    },
    { scope }
  )

  return (
    <div
      className="pointer-events-none flex w-full min-w-0 flex-col items-center justify-center px-2 py-8 text-center sm:px-6 lg:px-8"
      data-slot="aui_intro"
      ref={scope}
    >
      <div className="relative mb-6 flex items-center justify-center" data-intro-stagger>
        <span
          aria-hidden="true"
          className="absolute size-40 rounded-full bg-[radial-gradient(closest-side,color-mix(in_srgb,var(--ui-accent)_28%,transparent),transparent)] blur-xl"
          data-intro-halo
        />
        <BrandMark className="relative size-14 shadow-float" />
      </div>

      <h1
        className="m-0 mb-2 max-w-[34rem] bg-[linear-gradient(180deg,var(--ui-text-primary)_30%,color-mix(in_srgb,var(--ui-text-primary)_62%,var(--ui-accent)))] bg-clip-text text-[1.75rem] leading-[1.15] font-semibold tracking-[-0.025em] text-transparent"
        data-intro-stagger
      >
        {copy.headline}
      </h1>

      <p
        className="m-0 mb-7 max-w-[30rem] text-[0.875rem] leading-relaxed text-(--ui-text-secondary)"
        data-intro-stagger
      >
        {copy.body}
      </p>

      <IntroHints />
    </div>
  )
}
