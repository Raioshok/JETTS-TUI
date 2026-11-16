'use client'

import React from 'react'

import { GeneratedModelResult } from '@/components/chat/generated-model-result'
import { resolveModelDisplayUrl } from '@/lib/generated-models'

import type { RichFenceProps } from './types'

export default function BlenderEmbed({ code, streaming }: RichFenceProps) {
  if (streaming) {
    return (
      <div className="my-2 p-3 rounded-lg border border-violet-500/30 bg-(--ui-surface-background) text-xs font-mono text-violet-400">
        Streaming 3D model specification...
      </div>
    )
  }

  let modelUrl = ''
  let title = '3D Model'

  const trimmed = code.trim()

  if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
    try {
      const data = JSON.parse(trimmed)
      modelUrl = data.url || data.modelUrl || data.path || data.output_path || ''
      title = data.prompt || data.title || data.name || title
    } catch {
      // not valid json
    }
  } else {
    // Treat as bare path or URL
    modelUrl = trimmed.split('\n')[0].trim()
    title = modelUrl.split(/[\\/]/).pop() || '3D Asset'
  }

  const resolved = resolveModelDisplayUrl(modelUrl)

  return (
    <div className="my-2 max-w-xl">
      <GeneratedModelResult modelUrl={resolved} title={title} />
    </div>
  )
}
