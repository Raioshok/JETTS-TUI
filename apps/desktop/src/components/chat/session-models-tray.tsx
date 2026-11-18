import { useStore } from '@nanostores/react'
import { type FC, useEffect, useState } from 'react'

import { requestComposerInsert } from '@/app/chat/composer/focus'
import { useComposerScope } from '@/app/chat/composer/scope'
import { useSessionView } from '@/app/chat/session-view'
import { navigateWorkspaceHash } from '@/app/routes'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tip } from '@/components/ui/tooltip'
import { useI18n } from '@/i18n'
import { ESCAPE_PRIORITY, isTopEscapeLayer, pushEscapeLayer } from '@/lib/escape-layers'
import { studioDeepLinkHash } from '@/lib/generated-models'
import { Box, ChevronDown, ChevronRight, Download, ExternalLink, X, Zap } from '@/lib/icons'
import { cn } from '@/lib/utils'
import {
  $activePreviewModel,
  $session3DModels,
  $sessionModelsTrayOpen,
  $sessionModelsTrayScopes,
  $smart3DModalOpen,
  $smart3DModalScopes,
  type SessionModelRecord,
  setSessionModelsTrayOpen,
  setSmart3DModalOpen,
  toggleSessionModelsTray,
  toggleSmart3DModal
} from '@/store/blender-models'

interface SessionModelsTrayProps {
  sessionId?: null | string
}

export const SessionModelsTray: FC<SessionModelsTrayProps> = ({ sessionId }) => {
  const { t } = useI18n()
  const b3d = t.blender3d
  const scope = useComposerScope()
  const sessionView = useSessionView()
  const runtimeId = useStore(sessionView.$runtimeId)
  const activeSessionKey = sessionId || runtimeId || '__draft__'

  const allModels = useStore($session3DModels)
  const activePreview = useStore($activePreviewModel)
  const mainTrayOpen = useStore($sessionModelsTrayOpen)
  const scopedTrayMap = useStore($sessionModelsTrayScopes)
  const mainModalOpen = useStore($smart3DModalOpen)
  const scopedModalMap = useStore($smart3DModalScopes)

  const isOpen = scope.target === 'main' ? mainTrayOpen : Boolean(scopedTrayMap[scope.target])
  const showQuickModal = scope.target === 'main' ? mainModalOpen : Boolean(scopedModalMap[scope.target])
  const sessionModels = allModels[activeSessionKey] || []

  const [activePreset, setActivePreset] = useState<'abstract' | 'architecture' | 'furniture' | 'nature' | 'scifi'>(
    'nature'
  )

  const [quickPrompt, setQuickPrompt] = useState<string>('')

  const hasOpenLayer = showQuickModal || (isOpen && sessionModels.length > 0)

  useEffect(() => {
    if (!hasOpenLayer) {
      return
    }

    const release = pushEscapeLayer(ESCAPE_PRIORITY.composerPopover)

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || event.defaultPrevented || !isTopEscapeLayer(ESCAPE_PRIORITY.composerPopover)) {
        return
      }

      event.preventDefault()

      if (showQuickModal) {
        setSmart3DModalOpen(false, scope.target)

        return
      }

      setSessionModelsTrayOpen(false, scope.target)
    }

    window.addEventListener('keydown', onKeyDown)

    return () => {
      window.removeEventListener('keydown', onKeyDown)
      release()
    }
  }, [hasOpenLayer, scope.target, showQuickModal])

  if (sessionModels.length === 0 && !showQuickModal) {
    return null
  }

  const handleSelectModel = (model: SessionModelRecord) => {
    $activePreviewModel.set(model)
  }

  const handleInsertPrompt = (model: SessionModelRecord) => {
    requestComposerInsert(`Refine the 3D model "${model.name}": `, { target: scope.target })
  }

  const handleOpenStudio = (model?: SessionModelRecord) => {
    if (!model) {
      navigateWorkspaceHash('/blender')

      return
    }

    $activePreviewModel.set(model)
    navigateWorkspaceHash(
      studioDeepLinkHash({
        format: model.format,
        localPath: model.localPath,
        name: model.filename || model.name,
        url: model.url
      })
    )
  }

  const handleQuickGenerate = () => {
    if (!quickPrompt.trim()) {
      return
    }

    const formatted = `/3d [preset:${activePreset}] ${quickPrompt.trim()}`
    requestComposerInsert(formatted, { target: scope.target })
    setSmart3DModalOpen(false, scope.target)
    setQuickPrompt('')
  }

  const presets = [
    { id: 'nature', label: b3d.presets.nature },
    { id: 'scifi', label: b3d.presets.scifi },
    { id: 'architecture', label: b3d.presets.architecture },
    { id: 'furniture', label: b3d.presets.furniture },
    { id: 'abstract', label: b3d.presets.abstract }
  ] as const

  return (
    <div className="w-full px-2.5 py-1.5 select-none">
      {sessionModels.length > 0 && (
        <div className="flex items-center justify-between gap-2 py-0.5">
          <div className="flex min-w-0 items-center gap-2">
            <button
              aria-expanded={isOpen}
              className="flex cursor-pointer items-center gap-1.5 text-xs font-medium text-(--ui-text-primary) transition-colors hover:text-primary"
              onClick={() => toggleSessionModelsTray(scope.target)}
              type="button"
            >
              <Box className="size-3.5 text-primary" />
              <span>{b3d.sessionModels}</span>
              <span className="flex size-4 items-center justify-center rounded-full bg-primary/15 text-[0.625rem] font-semibold text-primary">
                {sessionModels.length}
              </span>
              {isOpen ? (
                <ChevronDown className="size-3 text-(--ui-text-tertiary)" />
              ) : (
                <ChevronRight className="size-3 text-(--ui-text-tertiary)" />
              )}
            </button>

            {!isOpen && (
              <div className="ml-1 hidden min-w-0 items-center gap-1 sm:flex">
                {sessionModels.slice(0, 3).map(m => (
                  <button
                    className={cn(
                      'max-w-30 cursor-pointer truncate rounded-md border px-2 py-0.5 text-[0.6875rem] transition-colors',
                      activePreview?.id === m.id
                        ? 'border-primary/50 bg-primary/10 text-(--ui-text-primary)'
                        : 'border-(--ui-stroke-tertiary) bg-(--ui-bg-card) text-(--ui-text-secondary) hover:bg-(--ui-control-hover-background) hover:text-(--ui-text-primary)'
                    )}
                    key={m.id}
                    onClick={() => {
                      setSessionModelsTrayOpen(true, scope.target)
                      handleSelectModel(m)
                    }}
                    type="button"
                  >
                    {m.name}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="flex shrink-0 items-center gap-1.5">
            <Tip label={b3d.smart3DTip}>
              <Button
                aria-expanded={showQuickModal}
                onClick={() => toggleSmart3DModal(scope.target)}
                size="xs"
                type="button"
                variant={showQuickModal ? 'secondary' : 'outline'}
              >
                <Zap className="size-3 text-primary" />
                <span>{b3d.smart3D}</span>
              </Button>
            </Tip>

            <Tip label={b3d.openStudioTip}>
              <Button onClick={() => handleOpenStudio()} size="xs" type="button" variant="ghost">
                <span>{b3d.studio}</span>
                <ExternalLink className="size-2.5" />
              </Button>
            </Tip>
          </div>
        </div>
      )}

      {isOpen && sessionModels.length > 0 && (
        <div className="mt-1.5 rounded-lg border border-(--ui-stroke-tertiary) bg-(--ui-bg-elevated) p-2.5">
          <div className="mb-2 flex items-center justify-between border-b border-(--ui-stroke-tertiary) pb-1.5 text-xs">
            <span className="font-medium text-(--ui-text-secondary)">{b3d.generatedModelsTitle}</span>
            <Button
              aria-label={t.common.close}
              className="size-5 p-0 text-(--ui-text-tertiary) hover:text-(--ui-text-primary)"
              onClick={() => setSessionModelsTrayOpen(false, scope.target)}
              size="icon"
              type="button"
              variant="ghost"
            >
              <X className="size-3.5" />
            </Button>
          </div>

          <div className="scrollbar-thin flex gap-2 overflow-x-auto pb-1">
            {sessionModels.map(model => {
              const selected = activePreview?.id === model.id

              return (
                <div
                  className={cn(
                    'group flex w-44 shrink-0 flex-col justify-between rounded-lg border p-2.5 transition-colors',
                    selected
                      ? 'border-primary/60 bg-primary/8'
                      : 'border-(--ui-stroke-tertiary) bg-(--ui-bg-card) hover:border-(--ui-stroke-secondary)'
                  )}
                  key={model.id}
                  onClick={() => handleSelectModel(model)}
                >
                  <div>
                    <div className="mb-1 flex items-center justify-between">
                      <span className="flex size-5 items-center justify-center rounded bg-primary/12 text-primary">
                        <Box className="size-3" />
                      </span>
                      <span className="font-mono text-[0.625rem] text-(--ui-text-tertiary) uppercase">
                        {model.format}
                      </span>
                    </div>
                    <div className="line-clamp-1 text-xs font-semibold text-(--ui-text-primary)">{model.name}</div>
                    <div className="mt-0.5 line-clamp-2 text-[0.6875rem] leading-snug text-(--ui-text-tertiary)">
                      {model.prompt || model.filename}
                    </div>
                  </div>

                  <div className="mt-2.5 flex items-center justify-between border-t border-(--ui-stroke-tertiary) pt-1.5">
                    <Tip label={b3d.iterateTip}>
                      <button
                        className="flex cursor-pointer items-center gap-1 text-[0.6875rem] font-medium text-primary transition-colors hover:opacity-80"
                        onClick={e => {
                          e.stopPropagation()
                          handleInsertPrompt(model)
                        }}
                        type="button"
                      >
                        <Zap className="size-2.5" />
                        <span>{b3d.iterate}</span>
                      </button>
                    </Tip>

                    <div className="flex items-center gap-0.5">
                      {model.url && (
                        <Tip label={b3d.downloadAsset}>
                          <a
                            aria-label={b3d.downloadAsset}
                            className="rounded p-1 text-(--ui-text-tertiary) transition-colors hover:bg-(--ui-control-hover-background) hover:text-(--ui-text-primary)"
                            download={model.filename}
                            href={model.url}
                            onClick={e => e.stopPropagation()}
                          >
                            <Download className="size-3" />
                          </a>
                        </Tip>
                      )}
                      <Tip label={b3d.inspectInStudio}>
                        <button
                          aria-label={b3d.inspectInStudio}
                          className="cursor-pointer rounded p-1 text-(--ui-text-tertiary) transition-colors hover:bg-(--ui-control-hover-background) hover:text-(--ui-text-primary)"
                          onClick={e => {
                            e.stopPropagation()
                            handleOpenStudio(model)
                          }}
                          type="button"
                        >
                          <ExternalLink className="size-3" />
                        </button>
                      </Tip>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {showQuickModal && (
        <div
          aria-label={b3d.smart3DTitle}
          className={cn(
            'rounded-lg border border-(--ui-stroke-secondary) bg-(--ui-bg-elevated) p-3',
            (sessionModels.length > 0 || isOpen) && 'mt-1.5'
          )}
          role="dialog"
        >
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Zap className="size-3.5 text-primary" />
              <span className="text-xs font-semibold text-(--ui-text-primary)">{b3d.smart3DTitle}</span>
            </div>
            <Button
              aria-label={t.common.close}
              className="size-5 p-0 text-(--ui-text-tertiary) hover:text-(--ui-text-primary)"
              onClick={() => setSmart3DModalOpen(false, scope.target)}
              size="icon"
              type="button"
              variant="ghost"
            >
              <X className="size-3.5" />
            </Button>
          </div>

          <div className="space-y-2.5">
            <Input
              autoFocus
              className="h-8 text-xs"
              onChange={e => setQuickPrompt(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  handleQuickGenerate()
                } else if (e.key === 'Escape') {
                  e.preventDefault()
                  e.stopPropagation()
                  setSmart3DModalOpen(false, scope.target)
                }
              }}
              placeholder={b3d.smart3DPlaceholder}
              type="text"
              value={quickPrompt}
            />

            <div className="flex flex-wrap items-center gap-1.5">
              {presets.map(p => (
                <button
                  aria-pressed={activePreset === p.id}
                  className={cn(
                    'cursor-pointer rounded-md border px-2 py-0.5 text-[0.6875rem] transition-colors',
                    activePreset === p.id
                      ? 'border-primary/50 bg-primary/12 font-semibold text-(--ui-text-primary)'
                      : 'border-(--ui-stroke-tertiary) text-(--ui-text-secondary) hover:bg-(--ui-control-hover-background) hover:text-(--ui-text-primary)'
                  )}
                  key={p.id}
                  onClick={() => setActivePreset(p.id)}
                  type="button"
                >
                  {p.label}
                </button>
              ))}
            </div>

            <div className="flex justify-end gap-2 pt-0.5">
              <Button onClick={() => setSmart3DModalOpen(false, scope.target)} size="xs" type="button" variant="ghost">
                {t.common.cancel}
              </Button>
              <Button disabled={!quickPrompt.trim()} onClick={handleQuickGenerate} size="xs" type="button">
                <Box className="size-3.5" />
                <span>{b3d.insertPrompt}</span>
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
