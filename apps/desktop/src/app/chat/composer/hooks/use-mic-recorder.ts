import { useEffect, useRef, useState } from 'react'

import { createSpeechGate } from '@/lib/voice-activity'

type BrowserAudioContext = typeof AudioContext

export interface MicRecorderOptions {
  onLevel?: (level: number) => void
  onError?: (error: Error) => void
  onSilence?: () => void
  silenceLevel?: number
  silenceMs?: number
  idleSilenceMs?: number
}

export interface MicRecording {
  audio: Blob
  durationMs: number
  heardSpeech: boolean
}

export interface MicRecorderErrorCopy {
  microphoneAccessDenied: string
  microphoneConstraintsUnsupported: string
  microphoneInUse: string
  microphonePermissionDenied: string
  microphoneStartFailed: string
  microphoneUnsupported: string
  noMicrophone: string
}

interface MicRecorderHandle {
  start: (options?: MicRecorderOptions) => Promise<void>
  stop: () => Promise<MicRecording | null>
  cancel: () => void
}

function micError(error: unknown, copy: MicRecorderErrorCopy): Error {
  const name = error instanceof DOMException ? error.name : ''

  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return new Error(copy.microphonePermissionDenied)
  }

  if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
    return new Error(copy.noMicrophone)
  }

  if (name === 'NotReadableError' || name === 'TrackStartError') {
    return new Error(copy.microphoneInUse)
  }

  if (name === 'OverconstrainedError') {
    return new Error(copy.microphoneConstraintsUnsupported)
  }

  if (error instanceof Error) {
    return error
  }

  return new Error(copy.microphoneStartFailed)
}

export function useMicRecorder(copy: MicRecorderErrorCopy): {
  handle: MicRecorderHandle
  level: number
  recording: boolean
} {
  const [level, setLevel] = useState(0)
  const [recording, setRecording] = useState(false)

  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const audioContextRef = useRef<AudioContext | null>(null)
  const animationRef = useRef<number | null>(null)
  const startedAtRef = useRef(0)
  const heardSpeechRef = useRef(false)
  const silenceTriggeredRef = useRef(false)
  const stopResolverRef = useRef<((recording: MicRecording | null) => void) | null>(null)

  const cleanup = () => {
    if (animationRef.current) {
      window.cancelAnimationFrame(animationRef.current)
      animationRef.current = null
    }

    void audioContextRef.current?.close()
    audioContextRef.current = null
    streamRef.current?.getTracks().forEach(track => track.stop())
    streamRef.current = null
    recorderRef.current = null
    setLevel(0)
    setRecording(false)
    silenceTriggeredRef.current = false
  }

  useEffect(() => () => cleanup(), [])

  const startMeter = (stream: MediaStream, options: MicRecorderOptions) => {
    const audioWindow = window as Window & { webkitAudioContext?: BrowserAudioContext }
    const AudioContextCtor = window.AudioContext || audioWindow.webkitAudioContext

    if (!AudioContextCtor) {
      return
    }

    try {
      const audioContext = new AudioContextCtor()
      const analyser = audioContext.createAnalyser()
      const source = audioContext.createMediaStreamSource(stream)

      analyser.fftSize = 256
      const data = new Uint8Array(analyser.fftSize)

      source.connect(analyser)
      audioContextRef.current = audioContext

      // Created after awaiting the mic, i.e. outside the click: Chromium may
      // start it suspended, which reads as permanent silence.
      if (audioContext.state === 'suspended') {
        void audioContext.resume().catch(() => undefined)
      }

      const speechThreshold = options.silenceLevel ?? 0

      const gate =
        speechThreshold > 0 && options.onSilence
          ? createSpeechGate(
              {
                idleSilenceMs: options.idleSilenceMs ?? 0,
                minSpeechLevel: speechThreshold,
                silenceMs: options.silenceMs ?? 0
              },
              startedAtRef.current
            )
          : null

      const tick = () => {
        analyser.getByteTimeDomainData(data)

        let sum = 0

        for (const value of data) {
          const centered = value - 128
          sum += centered * centered
        }

        const rms = Math.sqrt(sum / data.length)
        const normalized = Math.min(1, rms / 42)
        const now = Date.now()

        setLevel(normalized)
        options.onLevel?.(normalized)

        if (gate && options.onSilence && !silenceTriggeredRef.current) {
          const event = gate.update(normalized, now)
          heardSpeechRef.current = gate.heardSpeech

          if (event) {
            silenceTriggeredRef.current = true
            options.onSilence()

            return
          }
        }

        animationRef.current = window.requestAnimationFrame(tick)
      }

      tick()
    } catch {
      setLevel(0)
    }
  }

  const start: MicRecorderHandle['start'] = async (options = {}) => {
    if (recorderRef.current) {
      return
    }

    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      throw new Error(copy.microphoneUnsupported)
    }

    const permitted = await window.jettstuiDesktop?.requestMicrophoneAccess?.()

    if (permitted === false) {
      throw new Error(copy.microphoneAccessDenied)
    }

    let stream: MediaStream

    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true }
      })
    } catch (error) {
      throw micError(error, copy)
    }

    const mimeType =
      ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus', 'audio/ogg', 'audio/wav'].find(
        type => MediaRecorder.isTypeSupported(type)
      ) ?? ''

    let recorder: MediaRecorder

    try {
      recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
    } catch (error) {
      stream.getTracks().forEach(track => track.stop())
      throw micError(error, copy)
    }

    chunksRef.current = []
    streamRef.current = stream
    recorderRef.current = recorder
    heardSpeechRef.current = false
    silenceTriggeredRef.current = false
    startedAtRef.current = Date.now()

    recorder.ondataavailable = event => {
      if (event.data.size > 0) {
        chunksRef.current.push(event.data)
      }
    }

    recorder.onstop = () => {
      const chunks = chunksRef.current
      const recordingType = recorder.mimeType || mimeType || 'audio/webm'
      const durationMs = Date.now() - startedAtRef.current
      const heardSpeech = heardSpeechRef.current

      chunksRef.current = []
      cleanup()

      const resolver = stopResolverRef.current
      stopResolverRef.current = null

      if (!chunks.length) {
        resolver?.(null)

        return
      }

      resolver?.({
        audio: new Blob(chunks, { type: recordingType }),
        durationMs,
        heardSpeech
      })
    }

    recorder.onerror = event => {
      const error = micError((event as Event & { error?: unknown }).error, copy)
      const resolver = stopResolverRef.current
      stopResolverRef.current = null
      cleanup()
      options.onError?.(error)
      resolver?.(null)
    }

    recorder.start()
    setRecording(true)
    startMeter(stream, options)
  }

  const stop: MicRecorderHandle['stop'] = () =>
    new Promise<MicRecording | null>(resolve => {
      const recorder = recorderRef.current

      if (!recorder || recorder.state === 'inactive') {
        cleanup()
        resolve(null)

        return
      }

      stopResolverRef.current = resolve
      recorder.stop()
    })

  const cancel: MicRecorderHandle['cancel'] = () => {
    const recorder = recorderRef.current
    const resolver = stopResolverRef.current
    stopResolverRef.current = null

    if (recorder && recorder.state !== 'inactive') {
      recorder.ondataavailable = null
      recorder.onerror = null
      recorder.onstop = null
      recorder.stop()
    }

    cleanup()
    resolver?.(null)
  }

  const handle: MicRecorderHandle = { start, stop, cancel }

  return { handle, level, recording }
}
