import { useStore } from '@nanostores/react'
import { type FC, useState } from 'react'

import { requestComposerInsert } from '@/app/chat/composer/focus'
import { useSessionView } from '@/app/chat/session-view'
import { studioDeepLinkHash } from '@/lib/generated-models'
import { Box, ChevronDown, ChevronRight, Download, ExternalLink, X, Zap } from '@/lib/icons'
import { cn } from '@/lib/utils'
import {
  $activePreviewModel,
  $session3DModels,
  $sessionModelsTrayOpen,
  $smart3DModalOpen,
  type SessionModelRecord
} from '@/store/blender-models'

export const SessionModelsTray: FC = () => {
  const sessionView = useSessionView()
  const activeSessionId = useStore(sessionView.$runtimeId) || '__draft__'
  const allModels = useStore($session3DModels)
  const isOpen = useStore($sessionModelsTrayOpen)
  const showQuickModal = useStore($smart3DModalOpen)
  const sessionModels = allModels[activeSessionId] || []

  const [activePreset, setActivePreset] = useState<string>('nature')
  const [quickPrompt, setQuickPrompt] = useState<string>('')

  if (sessionModels.length === 0 && !showQuickModal) {
    return null
  }

  const handleSelectModel = (model: SessionModelRecord) => {
    $activePreviewModel.set(model)
  }

  const handleInsertPrompt = (model: SessionModelRecord) => {
    requestComposerInsert(`Refine the 3D model "${model.name}": `)
  }

  const handleOpenStudio = (model?: SessionModelRecord) => {
    if (!model) {
      window.location.hash = '#/blender'

      return
    }

    window.location.hash = studioDeepLinkHash({
      format: model.format,
      localPath: model.localPath,
      name: model.filename || model.name,
      url: model.url
    })
  }

  const handleQuickGenerate = () => {
    if (!quickPrompt.trim()) {
      return
    }

    const formatted = `/3d [preset:${activePreset}] ${quickPrompt.trim()}`
    requestComposerInsert(formatted)
    $smart3DModalOpen.set(false)
    setQuickPrompt('')
  }

  return (
    <div className="relative z-10 mb-2 w-full px-4 select-none">
      {sessionModels.length > 0 && (
        <div className="flex items-center justify-between rounded-lg border border-violet-500/30 bg-(--ui-surface-background)/90 px-3 py-1.5 shadow-md backdrop-blur-md">
          <div className="flex items-center gap-2">
            <button
              className="flex cursor-pointer items-center gap-1.5 text-xs font-medium text-violet-400 transition-colors hover:text-violet-300"
              onClick={() => $sessionModelsTrayOpen.set(!isOpen)}
              type="button"
            >
              <Box className="size-3.5" />
              <span>Session 3D Models</span>
              <span className="flex size-4 items-center justify-center rounded-full bg-violet-600/30 text-[0.62rem] font-bold text-violet-300">
                {sessionModels.length}
              </span>
              {isOpen ? (
                <ChevronDown className="size-3 text-zinc-400" />
              ) : (
                <ChevronRight className="size-3 text-zinc-400" />
              )}
            </button>

            {!isOpen && (
              <div className="ml-2 hidden items-center gap-1.5 sm:flex">
                {sessionModels.slice(0, 3).map(m => (
                  <span
                    className="max-w-[120px] cursor-pointer truncate rounded border border-(--ui-border) bg-(--ui-background) px-2 py-0.5 text-[0.68rem] text-zinc-300 hover:border-violet-500/50"
                    key={m.id}
                    onClick={() => {
                      $sessionModelsTrayOpen.set(true)
                      handleSelectModel(m)
                    }}
                    title={m.prompt || m.name}
                  >
                    {m.name}
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              className="flex cursor-pointer items-center gap-1 rounded border border-violet-500/30 bg-violet-600/20 px-2 py-1 text-[0.68rem] font-medium text-violet-300 transition-all hover:bg-violet-600/30"
              onClick={() => $smart3DModalOpen.set(!showQuickModal)}
              title="Create a new 3D model in this conversation"
              type="button"
            >
              <Zap className="size-3 text-violet-400" />
              <span>Smart 3D</span>
            </button>

            <button
              className="flex cursor-pointer items-center gap-1 text-[0.68rem] text-(--ui-text-tertiary) hover:text-(--ui-text-primary)"
              onClick={() => handleOpenStudio()}
              title="Open 3D Blender Studio"
              type="button"
            >
              <span>Studio</span>
              <ExternalLink className="size-2.5" />
            </button>
          </div>
        </div>
      )}

      {isOpen && sessionModels.length > 0 && (
        <div className="mt-1.5 rounded-xl border border-(--ui-border) bg-(--ui-panel-background)/95 p-3 shadow-xl backdrop-blur-md">
          <div className="mb-2 flex items-center justify-between border-b border-(--ui-border) pb-2 text-xs">
            <span className="font-medium text-zinc-400">Generated Models in this Chat</span>
            <button
              className="cursor-pointer rounded p-0.5 text-zinc-500 hover:text-zinc-300"
              onClick={() => $sessionModelsTrayOpen.set(false)}
              type="button"
            >
              <X className="size-3.5" />
            </button>
          </div>

          <div className="scrollbar-thin flex gap-2.5 overflow-x-auto pb-1">
            {sessionModels.map(model => (
              <div
                className="group flex w-44 shrink-0 flex-col justify-between rounded-lg border border-(--ui-border) bg-(--ui-surface-background)/80 p-2.5 transition-all hover:border-violet-500/60"
                key={model.id}
              >
                <div>
                  <div className="mb-1 flex items-center justify-between">
                    <span className="flex size-5 items-center justify-center rounded bg-violet-600/20 text-violet-400">
                      <Box className="size-3" />
                    </span>
                    <span className="font-mono text-[0.62rem] text-zinc-400 uppercase">{model.format}</span>
                  </div>
                  <div className="line-clamp-1 text-xs font-semibold text-(--ui-text-primary)" title={model.name}>
                    {model.name}
                  </div>
                  <div className="mt-0.5 line-clamp-2 text-[0.65rem] leading-snug text-zinc-500">
                    {model.prompt || model.filename}
                  </div>
                </div>

                <div className="mt-3 flex items-center justify-between border-t border-(--ui-border)/60 pt-2">
                  <button
                    className="flex cursor-pointer items-center gap-1 text-[0.65rem] font-medium text-violet-400 hover:text-violet-300"
                    onClick={() => handleInsertPrompt(model)}
                    title="Insert refinement prompt in chat composer"
                    type="button"
                  >
                    <Zap className="size-2.5" />
                    <span>Iterate</span>
                  </button>

                  <div className="flex items-center gap-1">
                    {model.url && (
                      <a
                        className="p-1 text-zinc-400 hover:text-zinc-200"
                        download={model.filename}
                        href={model.url}
                        title="Download asset"
                      >
                        <Download className="size-3" />
                      </a>
                    )}
                    <button
                      className="cursor-pointer p-1 text-zinc-400 hover:text-zinc-200"
                      onClick={() => handleOpenStudio(model)}
                      title="Inspect in 3D Studio"
                      type="button"
                    >
                      <ExternalLink className="size-3" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {showQuickModal && (
        <div className="mt-2 rounded-xl border border-violet-500/40 bg-(--ui-surface-background)/98 p-4 shadow-2xl backdrop-blur-md">
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Zap className="size-4 text-violet-400" />
              <span className="text-xs font-semibold text-white">Smart 3D Generator</span>
            </div>
            <button
              className="cursor-pointer text-zinc-400 hover:text-zinc-200"
              onClick={() => $smart3DModalOpen.set(false)}
              type="button"
            >
              <X className="size-3.5" />
            </button>
          </div>

          <div className="space-y-2.5">
            <input
              autoFocus
              className="w-full rounded-lg border border-(--ui-border) bg-(--ui-background) px-3 py-2 text-xs text-white placeholder:text-zinc-500 focus:border-violet-500 focus:outline-hidden"
              onChange={e => setQuickPrompt(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter') {
                  handleQuickGenerate()
                }
              }}
              placeholder="e.g. A low-poly medieval watchtower with torch..."
              type="text"
              value={quickPrompt}
            />

            <div className="flex flex-wrap items-center gap-1.5">
              {[
                { id: 'nature', label: '🌲 Nature' },
                { id: 'scifi', label: '🚀 Sci-Fi' },
                { id: 'architecture', label: '🏛️ Architecture' },
                { id: 'furniture', label: '🪑 Furniture' },
                { id: 'abstract', label: '🔮 Sculpture' }
              ].map(p => (
                <button
                  className={cn(
                    'cursor-pointer rounded border px-2 py-1 text-[0.68rem] transition-all',
                    activePreset === p.id
                      ? 'border-violet-500 bg-violet-500/20 font-semibold text-violet-300'
                      : 'border-(--ui-border) text-zinc-400 hover:bg-(--ui-hover)'
                  )}
                  key={p.id}
                  onClick={() => setActivePreset(p.id)}
                  type="button"
                >
                  {p.label}
                </button>
              ))}
            </div>

            <div className="flex justify-end gap-2 pt-1">
              <button
                className="cursor-pointer rounded px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200"
                onClick={() => $smart3DModalOpen.set(false)}
                type="button"
              >
                Cancel
              </button>
              <button
                className="flex cursor-pointer items-center gap-1.5 rounded-lg bg-violet-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-md transition-all hover:bg-violet-500 disabled:opacity-50"
                disabled={!quickPrompt.trim()}
                onClick={handleQuickGenerate}
                type="button"
              >
                <Box className="size-3.5" />
                <span>Insert Prompt</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
