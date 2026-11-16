import React, { FC, useState } from 'react'
import { useStore } from '@nanostores/react'

import { requestComposerInsert } from '@/app/chat/composer/focus'
import { Box, ChevronDown, ChevronRight, Download, ExternalLink, Zap, X } from '@/lib/icons'
import {
  $activePreviewModel,
  $session3DModels,
  $sessionModelsTrayOpen,
  type SessionModelRecord
} from '@/store/blender-models'
import { $activeSessionId } from '@/store/session'
import { cn } from '@/lib/utils'

export const SessionModelsTray: FC = () => {
  const activeSessionId = useStore($activeSessionId) || '__draft__'
  const allModels = useStore($session3DModels)
  const isOpen = useStore($sessionModelsTrayOpen)
  const sessionModels = allModels[activeSessionId] || []

  const [activePreset, setActivePreset] = useState<string>('nature')
  const [showQuickModal, setShowQuickModal] = useState<boolean>(false)
  const [quickPrompt, setQuickPrompt] = useState<string>('')

  if (sessionModels.length === 0 && !showQuickModal) {
    return null
  }

  const handleSelectModel = (model: SessionModelRecord) => {
    $activePreviewModel.set(model)
  }

  const handleInsertPrompt = (model: SessionModelRecord) => {
    const text = `Refine the 3D model "${model.name}": `
    requestComposerInsert(text)
  }

  const handleOpenStudio = (model?: SessionModelRecord) => {
    window.location.hash = '#/blender'
  }

  const handleQuickGenerate = () => {
    if (!quickPrompt.trim()) return
    const formatted = `/3d [preset:${activePreset}] ${quickPrompt.trim()}`
    requestComposerInsert(formatted)
    setShowQuickModal(false)
    setQuickPrompt('')
  }

  return (
    <div className="relative w-full px-4 mb-2 select-none z-10">
      {/* Floating Tray Toggle Bar */}
      <div className="flex items-center justify-between rounded-lg border border-violet-500/30 bg-(--ui-surface-background)/90 px-3 py-1.5 backdrop-blur-md shadow-md">
        <div className="flex items-center gap-2">
          <button
            onClick={() => $sessionModelsTrayOpen.set(!isOpen)}
            className="flex items-center gap-1.5 text-xs font-medium text-violet-400 hover:text-violet-300 transition-colors cursor-pointer"
          >
            <Box className="size-3.5" />
            <span>Session 3D Models</span>
            <span className="flex size-4 items-center justify-center rounded-full bg-violet-600/30 text-[0.62rem] font-bold text-violet-300">
              {sessionModels.length}
            </span>
            {isOpen ? <ChevronDown className="size-3 text-zinc-400" /> : <ChevronRight className="size-3 text-zinc-400" />}
          </button>

          {/* Quick thumbnail peek */}
          {!isOpen && sessionModels.length > 0 && (
            <div className="hidden sm:flex items-center gap-1.5 ml-2">
              {sessionModels.slice(0, 3).map(m => (
                <span
                  key={m.id}
                  onClick={() => {
                    $sessionModelsTrayOpen.set(true)
                    handleSelectModel(m)
                  }}
                  className="px-2 py-0.5 rounded bg-(--ui-background) border border-(--ui-border) text-[0.68rem] text-zinc-300 truncate max-w-[120px] cursor-pointer hover:border-violet-500/50"
                  title={m.prompt || m.name}
                >
                  {m.name}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Right Action buttons */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowQuickModal(true)}
            className="flex items-center gap-1 px-2 py-1 rounded bg-violet-600/20 hover:bg-violet-600/30 text-violet-300 border border-violet-500/30 text-[0.68rem] font-medium transition-all cursor-pointer"
            title="Create a new 3D model in this conversation"
          >
            <Zap className="size-3 text-violet-400" />
            <span>Smart 3D</span>
          </button>

          <button
            onClick={() => handleOpenStudio()}
            className="flex items-center gap-1 text-[0.68rem] text-(--ui-text-tertiary) hover:text-(--ui-text-primary) cursor-pointer"
            title="Open 3D Blender Studio"
          >
            <span>Studio</span>
            <ExternalLink className="size-2.5" />
          </button>
        </div>
      </div>

      {/* Expanded History Reel */}
      {isOpen && (
        <div className="mt-1.5 rounded-xl border border-(--ui-border) bg-(--ui-panel-background)/95 p-3 shadow-xl backdrop-blur-md">
          <div className="flex items-center justify-between pb-2 mb-2 border-b border-(--ui-border) text-xs">
            <span className="text-zinc-400 font-medium">Generated Models in this Chat</span>
            <button
              onClick={() => $sessionModelsTrayOpen.set(false)}
              className="text-zinc-500 hover:text-zinc-300 p-0.5 rounded cursor-pointer"
            >
              <X className="size-3.5" />
            </button>
          </div>

          <div className="flex gap-2.5 overflow-x-auto pb-1 scrollbar-thin">
            {sessionModels.map(model => (
              <div
                key={model.id}
                className="flex flex-col justify-between w-44 shrink-0 rounded-lg border border-(--ui-border) bg-(--ui-surface-background)/80 p-2.5 hover:border-violet-500/60 transition-all group"
              >
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="flex size-5 items-center justify-center rounded bg-violet-600/20 text-violet-400">
                      <Box className="size-3" />
                    </span>
                    <span className="text-[0.62rem] font-mono text-zinc-400 uppercase">
                      {model.format}
                    </span>
                  </div>
                  <div className="text-xs font-semibold text-(--ui-text-primary) line-clamp-1" title={model.name}>
                    {model.name}
                  </div>
                  <div className="text-[0.65rem] text-zinc-500 line-clamp-2 mt-0.5 leading-snug">
                    {model.prompt || model.filename}
                  </div>
                </div>

                <div className="flex items-center justify-between mt-3 pt-2 border-t border-(--ui-border)/60">
                  <button
                    onClick={() => handleInsertPrompt(model)}
                    className="flex items-center gap-1 text-[0.65rem] text-violet-400 hover:text-violet-300 font-medium cursor-pointer"
                    title="Insert refinement prompt in chat composer"
                  >
                    <Zap className="size-2.5" />
                    <span>Iterate</span>
                  </button>

                  <div className="flex items-center gap-1">
                    {model.url && (
                      <a
                        href={model.url}
                        download={model.filename}
                        className="p-1 text-zinc-400 hover:text-zinc-200"
                        title="Download asset"
                      >
                        <Download className="size-3" />
                      </a>
                    )}
                    <button
                      onClick={() => handleOpenStudio(model)}
                      className="p-1 text-zinc-400 hover:text-zinc-200 cursor-pointer"
                      title="Inspect in 3D Studio"
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

      {/* Quick 3D Generation Dialog */}
      {showQuickModal && (
        <div className="mt-2 rounded-xl border border-violet-500/40 bg-(--ui-surface-background)/98 p-4 shadow-2xl backdrop-blur-md">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Zap className="size-4 text-violet-400" />
              <span className="text-xs font-semibold text-white">Smart 3D Generator</span>
            </div>
            <button
              onClick={() => setShowQuickModal(false)}
              className="text-zinc-400 hover:text-zinc-200 cursor-pointer"
            >
              <X className="size-3.5" />
            </button>
          </div>

          <div className="space-y-2.5">
            <input
              type="text"
              value={quickPrompt}
              onChange={e => setQuickPrompt(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter') handleQuickGenerate()
              }}
              placeholder="e.g. A low-poly medieval watchtower with torch..."
              className="w-full rounded-lg border border-(--ui-border) bg-(--ui-background) px-3 py-2 text-xs text-white placeholder:text-zinc-500 focus:border-violet-500 focus:outline-hidden"
              autoFocus
            />

            {/* Presets */}
            <div className="flex items-center gap-1.5 flex-wrap">
              {[
                { id: 'nature', label: '🌲 Nature' },
                { id: 'scifi', label: '🚀 Sci-Fi' },
                { id: 'architecture', label: '🏛️ Architecture' },
                { id: 'furniture', label: '🪑 Furniture' },
                { id: 'abstract', label: '🔮 Sculpture' }
              ].map(p => (
                <button
                  key={p.id}
                  onClick={() => setActivePreset(p.id)}
                  className={cn(
                    'px-2 py-1 rounded text-[0.68rem] border transition-all cursor-pointer',
                    activePreset === p.id
                      ? 'border-violet-500 bg-violet-500/20 text-violet-300 font-semibold'
                      : 'border-(--ui-border) text-zinc-400 hover:bg-(--ui-hover)'
                  )}
                >
                  {p.label}
                </button>
              ))}
            </div>

            <div className="flex justify-end gap-2 pt-1">
              <button
                onClick={() => setShowQuickModal(false)}
                className="px-3 py-1.5 rounded text-xs text-zinc-400 hover:text-zinc-200 cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={handleQuickGenerate}
                disabled={!quickPrompt.trim()}
                className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white text-xs font-semibold shadow-md cursor-pointer transition-all"
              >
                <Box className="size-3.5" />
                <span>Send to Chat</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
