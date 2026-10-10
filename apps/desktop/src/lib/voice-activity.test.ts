import { describe, expect, it } from 'vitest'

import { createSpeechGate, type SpeechGateEvent } from './voice-activity'

const OPTIONS = { idleSilenceMs: 12_000, minSpeechLevel: 0.075, silenceMs: 1_250 }
const FRAME_MS = 16

/** Feed `[level, durationMs]` segments at ~60 fps; return the first event and when it fired. */
function run(segments: [number, number][]): { at: number; event: SpeechGateEvent } {
  const gate = createSpeechGate(OPTIONS, 0)
  let now = 0

  for (const [level, duration] of segments) {
    const end = now + duration

    for (; now < end; now += FRAME_MS) {
      const event = gate.update(level, now)

      if (event) {
        return { at: now, event }
      }
    }
  }

  return { at: now, event: null }
}

describe('createSpeechGate', () => {
  it('ends the turn shortly after speech in a quiet room', () => {
    const { at, event } = run([
      [0.01, 500],
      [0.4, 2_000],
      [0.01, 5_000]
    ])

    expect(event).toBe('end-of-speech')
    expect(at).toBeLessThan(2_500 + OPTIONS.silenceMs + 200)
  })

  it('ends the turn in a noisy room whose background is above the fixed threshold', () => {
    // Fan / hum at 0.15 — louder than minSpeechLevel, so a fixed threshold
    // never sees silence and the turn would only end at the hard timeout.
    const { at, event } = run([
      [0.15, 800],
      [0.6, 2_000],
      [0.15, 5_000]
    ])

    expect(event).toBe('end-of-speech')
    expect(at).toBeLessThan(2_800 + OPTIONS.silenceMs + 200)
  })

  it('does not mistake steady background noise for speech', () => {
    const { at, event } = run([[0.15, 15_000]])

    expect(event).toBe('no-speech')
    expect(at).toBeGreaterThanOrEqual(OPTIONS.idleSilenceMs)
  })

  it('keeps listening through short pauses between words', () => {
    const { event } = run([
      [0.01, 300],
      [0.4, 800],
      [0.01, 600],
      [0.4, 800]
    ])

    expect(event).toBeNull()
  })
})
