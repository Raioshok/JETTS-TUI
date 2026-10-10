/**
 * End-of-utterance detection for the voice conversation loop.
 *
 * A fixed level threshold breaks in real rooms: with a fan, a laptop hum, or a
 * high mic gain the background alone stays above it, so "silence" never comes
 * and the turn only ends at the hard timeout. This gate tracks the room's
 * noise floor while nobody is speaking and judges speech and silence relative
 * to it (with hysteresis), so a turn ends shortly after the user stops talking
 * in quiet and noisy rooms alike.
 */

export interface SpeechGateOptions {
  /** Absolute minimum level (0–1) that counts as speech, even in a silent room. */
  minSpeechLevel: number
  /** Quiet time after speech that ends the utterance. */
  silenceMs: number
  /** Give up when nothing was said for this long (0 = never). */
  idleSilenceMs: number
}

export type SpeechGateEvent = 'end-of-speech' | 'no-speech' | null

export interface SpeechGate {
  readonly heardSpeech: boolean
  /** Feed one meter reading (0–1); returns an event when the turn should end. */
  update: (level: number, now: number) => SpeechGateEvent
}

// Speech must clearly stand out from the floor; silence is "back near the floor".
const SPEECH_FLOOR_RATIO = 1.8
const SPEECH_MARGIN = 0.03
const SILENCE_FLOOR_RATIO = 1.35
const SILENCE_MARGIN = 0.015

export function createSpeechGate(options: SpeechGateOptions, startedAt: number): SpeechGate {
  let floor: null | number = null
  let heardSpeech = false
  let silenceSince: null | number = null

  const speechThreshold = () => Math.max(options.minSpeechLevel, (floor ?? 0) * SPEECH_FLOOR_RATIO + SPEECH_MARGIN)

  const silenceThreshold = () =>
    Math.min(
      speechThreshold(),
      Math.max(options.minSpeechLevel * 0.8, (floor ?? 0) * SILENCE_FLOOR_RATIO + SILENCE_MARGIN)
    )

  return {
    get heardSpeech() {
      return heardSpeech
    },

    update(level, now) {
      // Noise floor: follow drops quickly, creep up slowly, and never learn
      // from speech (readings above the speech threshold are ignored).
      if (floor === null) {
        floor = level
      } else if (level < floor) {
        floor = floor * 0.7 + level * 0.3
      } else if (level < speechThreshold()) {
        floor = floor * 0.98 + level * 0.02
      }

      if (level >= speechThreshold()) {
        heardSpeech = true
        silenceSince = null

        return null
      }

      if (heardSpeech) {
        if (level < silenceThreshold()) {
          silenceSince ??= now

          return now - silenceSince >= options.silenceMs ? 'end-of-speech' : null
        }

        silenceSince = null

        return null
      }

      return options.idleSilenceMs > 0 && now - startedAt >= options.idleSilenceMs ? 'no-speech' : null
    }
  }
}
