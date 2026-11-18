'use client'

import { GeneratedModelResult } from '@/components/chat/generated-model-result'
import { Loader } from '@/components/ui/loader'
import { useI18n } from '@/i18n'
import { resolveModelDisplayUrl } from '@/lib/generated-models'

import type { RichFenceProps } from './types'

export default function BlenderEmbed({ code, streaming }: RichFenceProps) {
  const { t } = useI18n()

  if (streaming) {
    return (
      <div className="my-2 flex items-center gap-2 rounded-lg border border-(--ui-stroke-tertiary) bg-(--ui-bg-elevated) px-3 py-2 text-xs text-(--ui-text-secondary)">
        <Loader className="size-4 shrink-0" />
        <span>{t.blender3d.streamingSpec}</span>
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
