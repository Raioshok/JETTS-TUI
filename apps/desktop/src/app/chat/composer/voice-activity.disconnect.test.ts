import { describe, expect, it, vi } from 'vitest'

import { disconnectAudioGraph } from '@/app/chat/composer/voice-activity'

type GraphEntry = Parameters<typeof disconnectAudioGraph>[0]

/**
 * The playback waveform builds a MediaElementSourceNode + AnalyserNode and
 * connects them to a module-singleton AudioContext that is never closed. The
 * source node pins the <audio> element (and its decoded PCM), so each TTS reply
 * used to leak one node-pair + element for the app's life. The waveform effect
 * now disconnects the graph on cleanup; this proves that teardown.
 */
describe('disconnectAudioGraph', () => {
  it('disconnects both the source and the analyser so the context releases them', () => {
    const source = { disconnect: vi.fn() }
    const analyser = { disconnect: vi.fn() }

    disconnectAudioGraph({ analyser, source } as unknown as GraphEntry)

    expect(source.disconnect).toHaveBeenCalledTimes(1)
    expect(analyser.disconnect).toHaveBeenCalledTimes(1)
  })

  it('tolerates a repeated teardown (a second disconnect throws)', () => {
    const source = {
      disconnect: vi.fn(() => {
        throw new DOMException('already disconnected')
      })
    }

    const analyser = { disconnect: vi.fn() }

    expect(() => disconnectAudioGraph({ analyser, source } as unknown as GraphEntry)).not.toThrow()
    expect(source.disconnect).toHaveBeenCalledTimes(1)
  })
})
