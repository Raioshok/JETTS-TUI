import { Box, stringWidth, Text, useStdout } from '@jetts-tui/ink'
import { useStore } from '@nanostores/react'
import type { ReactNode } from 'react'

import { useGateway } from '../app/gatewayContext.js'
import type { AppOverlaysProps } from '../app/interfaces.js'
import { $overlayState, patchOverlayState } from '../app/overlayStore.js'
import { $uiSessionId, $uiTheme } from '../app/uiStore.js'

import { ActiveSessionSwitcher } from './activeSessionSwitcher.js'
import { FloatBox } from './appChrome.js'
import { MaskedPrompt } from './maskedPrompt.js'
import { ModelPicker } from './modelPicker.js'
import { OverlayHint } from './overlayControls.js'
import { listRowStyle } from './overlayPrimitives.js'
import { PetPicker } from './petPicker.js'
import { PluginsHub } from './pluginsHub.js'
import { ApprovalPrompt, ClarifyPrompt, ConfirmPrompt } from './prompts.js'
import { SkillsHub } from './skillsHub.js'
import { WidgetGrid, type WidgetGridWidget } from './widgetGrid.js'

const COMPLETION_WINDOW = 16

/**
 * A prompt hosted in a single-cell WidgetGrid with the classic 1-cell padding.
 * The inner full-width column restores the horizontal stretch the old plain
 * padded Box gave its child, so rendering is identical; routing through the
 * grid makes the prompt zone a layout-engine surface like the desktop app's
 * pane shell.
 */
function PromptCell({ children, cols, id }: { children: ReactNode; cols: number; id: string }) {
  return (
    <Box flexDirection="column" flexShrink={0}>
      <WidgetGrid
        cols={cols}
        columns={1}
        gap={0}
        paddingX={1}
        paddingY={1}
        rowGap={0}
        widgets={[
          {
            children: (
              <Box flexDirection="column" width="100%">
                {children}
              </Box>
            ),
            id
          }
        ]}
      />
    </Box>
  )
}

export function PromptZone({
  cols,
  onApprovalChoice,
  onClarifyAnswer,
  onSecretSubmit,
  onSudoSubmit
}: Pick<AppOverlaysProps, 'cols' | 'onApprovalChoice' | 'onClarifyAnswer' | 'onSecretSubmit' | 'onSudoSubmit'>) {
  const overlay = useStore($overlayState)
  const theme = useStore($uiTheme)

  if (overlay.approval) {
    return (
      <PromptCell cols={cols} id="approval">
        <ApprovalPrompt cols={cols} onChoice={onApprovalChoice} req={overlay.approval} t={theme} />
      </PromptCell>
    )
  }

  if (overlay.confirm) {
    const req = overlay.confirm

    const onConfirm = () => {
      patchOverlayState({ confirm: null })
      req.onConfirm()
    }

    const onCancel = () => patchOverlayState({ confirm: null })

    return (
      <PromptCell cols={cols} id="confirm">
        <ConfirmPrompt onCancel={onCancel} onConfirm={onConfirm} req={req} t={theme} />
      </PromptCell>
    )
  }

  if (overlay.clarify) {
    return (
      <PromptCell cols={cols} id="clarify">
        <ClarifyPrompt
          cols={cols}
          onAnswer={onClarifyAnswer}
          onCancel={() => onClarifyAnswer('')}
          req={overlay.clarify}
          t={theme}
        />
      </PromptCell>
    )
  }

  if (overlay.sudo) {
    return (
      <PromptCell cols={cols} id="sudo">
        <MaskedPrompt cols={cols} icon="🔐" label="sudo password required" onSubmit={onSudoSubmit} t={theme} />
      </PromptCell>
    )
  }

  if (overlay.secret) {
    return (
      <PromptCell cols={cols} id="secret">
        <MaskedPrompt
          cols={cols}
          icon="🔑"
          label={overlay.secret.prompt}
          onSubmit={onSecretSubmit}
          sub={`for ${overlay.secret.envVar}`}
          t={theme}
        />
      </PromptCell>
    )
  }

  return null
}

export function FloatingOverlays({
  cols,
  compIdx,
  completions,
  onActiveSessionSelect,
  onActiveSessionClose,
  onModelSelect,
  onNewLiveSession,
  onNewPromptSession,
  onResumeSelect,
  pagerPageSize
}: Pick<
  AppOverlaysProps,
  | 'cols'
  | 'compIdx'
  | 'completions'
  | 'onActiveSessionSelect'
  | 'onActiveSessionClose'
  | 'onModelSelect'
  | 'onNewLiveSession'
  | 'onNewPromptSession'
  | 'onResumeSelect'
  | 'pagerPageSize'
>) {
  const { gw } = useGateway()
  const { stdout } = useStdout()
  const overlay = useStore($overlayState)
  const sid = useStore($uiSessionId)
  const theme = useStore($uiTheme)

  const hasModalOverlay = Boolean(
    overlay.modelPicker ||
    overlay.pager ||
    overlay.petPicker ||
    overlay.sessions ||
    overlay.skillsHub ||
    overlay.pluginsHub
  )

  const showCompletions = !hasModalOverlay && completions.length > 0
  const hasAny = hasModalOverlay || showCompletions

  if (!hasAny) {
    return null
  }

  // Clamp completion window to terminal height so short split panes never clip
  // the top of the completion list above row 0.
  const completionWindow = Math.max(4, Math.min(COMPLETION_WINDOW, (stdout?.rows ?? 24) - 10))

  // Fixed viewport centered on compIdx — previously the slice end was
  // compIdx + 8 so the dropdown grew from 8 rows to 16 as the user scrolled
  // down, bouncing the height on every keystroke.
  const viewportSize = Math.min(completionWindow, completions.length)

  const start = Math.max(0, Math.min(compIdx - Math.floor(completionWindow / 2), completions.length - viewportSize))

  // Subtract FloatBox chrome (2 border cols + 2 padding cols = 4) from each
  // child panel's maxWidth so panels never overflow the terminal's right edge.
  const innerBudget = (cellWidth: number) => Math.max(16, cellWidth - 4)

  // Every floating panel is a widget in a single-column grid. Panels keep
  // their intrinsic (content-hugging) widths inside full-width cells today;
  // multi-column tiling on wide terminals is a `columns`/track change here,
  // not a rewrite. `maxWidth` hands each panel its cell budget — with one
  // column it never binds, so rendering is identical to the pre-grid layout.
  const widgets: WidgetGridWidget[] = []

  if (overlay.sessions) {
    widgets.push({
      id: 'sessions',
      render: width => (
        <FloatBox color={theme.color.border}>
          <ActiveSessionSwitcher
            currentSessionId={sid}
            gw={gw}
            maxWidth={innerBudget(width)}
            onCancel={() => patchOverlayState({ sessions: false })}
            onClose={onActiveSessionClose}
            onNew={onNewLiveSession}
            onNewPrompt={onNewPromptSession}
            onResume={onResumeSelect}
            onSelect={onActiveSessionSelect}
            t={theme}
          />
        </FloatBox>
      )
    })
  }

  if (overlay.modelPicker) {
    const initialRefresh = typeof overlay.modelPicker === 'object' && overlay.modelPicker.refresh === true

    widgets.push({
      id: 'model-picker',
      render: width => (
        <FloatBox color={theme.color.border}>
          <ModelPicker
            gw={gw}
            initialRefresh={initialRefresh}
            maxWidth={innerBudget(width)}
            onCancel={() => patchOverlayState({ modelPicker: false })}
            onSelect={onModelSelect}
            sessionId={sid}
            t={theme}
          />
        </FloatBox>
      )
    })
  }

  if (overlay.petPicker) {
    widgets.push({
      id: 'pet-picker',
      render: width => (
        <FloatBox color={theme.color.border}>
          <PetPicker
            gw={gw}
            maxWidth={innerBudget(width)}
            onClose={() => patchOverlayState({ petPicker: false })}
            t={theme}
          />
        </FloatBox>
      )
    })
  }

  if (overlay.skillsHub) {
    widgets.push({
      id: 'skills-hub',
      render: width => (
        <FloatBox color={theme.color.border}>
          <SkillsHub
            gw={gw}
            maxWidth={innerBudget(width)}
            onClose={() => patchOverlayState({ skillsHub: false })}
            t={theme}
          />
        </FloatBox>
      )
    })
  }

  if (overlay.pluginsHub) {
    widgets.push({
      id: 'plugins-hub',
      render: width => (
        <FloatBox color={theme.color.border}>
          <PluginsHub
            gw={gw}
            maxWidth={innerBudget(width)}
            onClose={() => patchOverlayState({ pluginsHub: false })}
            t={theme}
          />
        </FloatBox>
      )
    })
  }

  const pager = overlay.pager

  if (pager) {
    widgets.push({
      id: 'pager',
      render: () => (
        <FloatBox color={theme.color.border}>
          <Box flexDirection="column" paddingX={1} paddingY={1}>
            {pager.title && (
              <Box justifyContent="center" marginBottom={1}>
                <Text bold color={theme.color.primary}>
                  {pager.title}
                </Text>
              </Box>
            )}

            {pager.lines.slice(pager.offset, pager.offset + pagerPageSize).map((line, i) => (
              <Text key={i}>{line}</Text>
            ))}

            <Box marginTop={1}>
              <OverlayHint t={theme}>
                {pager.offset + pagerPageSize < pager.lines.length
                  ? `↑↓/jk line · Enter/Space/PgDn page · b/PgUp back · g/G top/bottom · Esc/q close (${Math.min(pager.offset + pagerPageSize, pager.lines.length)}/${pager.lines.length})`
                  : `end · ↑↓/jk · b/PgUp back · g top · Esc/q close (${pager.lines.length} lines)`}
              </OverlayHint>
            </Box>
          </Box>
        </FloatBox>
      )
    })
  }

  if (showCompletions) {
    const boxWidth = Math.max(16, cols - 6)

    widgets.push({
      id: 'completions',
      render: () => (
        <FloatBox color={theme.color.primary}>
          {/* No painted panel fill: FloatBox is `opaque`, so rows sit on the
              terminal's own background — the one color that is always right
              on a canvas we don't own (a full completionBg fill was the lone
              surface painting its own background, which is why it could
              disagree with every other overlay). Only the ACTIVE row carries
              a selection chip, mirroring the session switcher. */}
          <Box flexDirection="column" width={boxWidth}>
            {(() => {
              const visible = completions.slice(start, start + viewportSize)
              // Two-column grid: the name track auto-sizes to the widest
              // visible command (capped on narrow viewports), so descriptions align.
              const rawNameW = Math.max(...visible.map(item => stringWidth(item.display))) + 2
              const nameW = Math.min(Math.max(10, Math.floor(boxWidth * 0.55)), rawNameW)

              return visible.map((item, i) => {
                const active = start + i === compIdx
                const row = listRowStyle(theme, active)

                return (
                  <Box
                    backgroundColor={row.backgroundColor}
                    flexDirection="row"
                    key={`${start + i}:${item.text}:${item.display}:${item.meta ?? ''}`}
                    width="100%"
                  >
                    <Box flexShrink={0} width={nameW}>
                      <Text
                        backgroundColor={row.backgroundColor}
                        bold
                        color={active ? (row.color ?? theme.color.label) : theme.color.label}
                        wrap="truncate-end"
                      >
                        {' '}
                        {item.display}
                      </Text>
                    </Box>
                    {item.meta ? (
                      // Descriptions in the neutral gray, NOT a gold-family
                      // tone — label vs muted are near-twins on some skins,
                      // which made command and description read as one run.
                      // Active row: meta rides the chip, so it uses row ink.
                      <Text
                        backgroundColor={row.backgroundColor}
                        color={active ? row.color : theme.color.statusFg}
                        wrap="truncate-end"
                      >
                        {item.meta}
                      </Text>
                    ) : null}
                  </Box>
                )
              })
            })()}
          </Box>
        </FloatBox>
      )
    })
  }

  return (
    <Box alignItems="flex-start" bottom="100%" flexDirection="column" left={0} position="absolute" right={0}>
      <WidgetGrid cols={cols} columns={1} gap={0} paddingX={0} paddingY={0} rowGap={0} widgets={widgets} />
    </Box>
  )
}
