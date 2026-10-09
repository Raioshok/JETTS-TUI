import React from 'react'
import { describe, expect, it } from 'vitest'

import { residentSessionTargetForHotkey } from '../app/useInputHandlers.js'
import {
  residentCurrentSessionIndex,
  ResidentInputTarget,
  residentSessionLabel,
  ResidentSessionPreview,
  ResidentWorkspaceSidebar,
  shouldUseResidentWorkspace
} from '../components/residentWorkspace.js'
import type { SessionActiveItem } from '../gatewayTypes.js'
import { DEFAULT_THEME } from '../theme.js'

const textContent = (node: React.ReactNode): string => {
  if (node === null || node === undefined || typeof node === 'boolean') {return ''}

  if (typeof node === 'string' || typeof node === 'number') {return String(node)}

  if (Array.isArray(node)) {return node.map(textContent).join('')}

  return React.isValidElement(node) ? textContent(node.props.children) : ''
}

const sessions: SessionActiveItem[] = [
  {
    current: false,
    id: 'research',
    message_count: 4,
    model: 'openai/gpt-5.6-luna',
    preview: 'Comparing provider pricing',
    status: 'working',
    title: 'Research'
  },
  {
    current: true,
    id: 'build',
    message_count: 12,
    model: 'anthropic/claude-sonnet',
    preview: 'Implementing the TUI workspace',
    status: 'idle',
    title: 'Build'
  }
]

describe('resident workspace responsiveness', () => {
  it('activates only when the terminal can hold the full workspace', () => {
    expect(shouldUseResidentWorkspace(140, 40, 2)).toBe(true)
    expect(shouldUseResidentWorkspace(100, 40, 2)).toBe(false)
    expect(shouldUseResidentWorkspace(140, 24, 2)).toBe(false)
    expect(shouldUseResidentWorkspace(140, 40, 0)).toBe(false)
  })

  it('honors the explicit resident_workspace preference', () => {
    expect(shouldUseResidentWorkspace(140, 40, 2, 'off')).toBe(false)
    expect(shouldUseResidentWorkspace(100, 24, 1, 'on')).toBe(true)
    expect(shouldUseResidentWorkspace(100, 24, 0, 'on')).toBe(false)
    expect(shouldUseResidentWorkspace(140, 40, 2, 'auto')).toBe(true)
  })

  it('uses stable fallback agent names', () => {
    expect(residentSessionLabel(sessions[0]!, 0)).toBe('Research')
    expect(residentSessionLabel({ ...sessions[0]!, title: '' }, 2)).toBe('agent3')
  })

  it('maps Alt+1…9 to a stable session target', () => {
    expect(residentSessionTargetForHotkey('2', true, sessions)?.id).toBe('build')
    expect(residentSessionTargetForHotkey('2', false, sessions)).toBeUndefined()
    expect(residentSessionTargetForHotkey('9', true, sessions)).toBeUndefined()
  })

  it('prefers the explicit target while polling still marks the old session current', () => {
    const stale = sessions.map((session, index) => ({ ...session, current: index === 0 }))

    expect(residentCurrentSessionIndex(stale, 'build')).toBe(1)
  })
})

describe('resident workspace surfaces', () => {
  it('shows live sessions, comms, and discoverable controls', () => {
    const frame = textContent(
      ResidentWorkspaceSidebar({
        currentSessionId: 'build',
        onNew: () => {},
        onOpenAgents: () => {},
        onSelect: () => {},
        sessions,
        subagents: [],
        t: DEFAULT_THEME,
        unread: new Map()
      })
    )

    expect(frame).toContain('Sessions')
    expect(frame).toContain('Comms')
    expect(frame).toContain('Research')
    expect(frame).toContain('Build')
    expect(frame).toContain('Alt+1…9 target')
    expect(frame).toContain('Comparing provider pricing')
  })

  it('shows an unread badge for background growth and a dot for a count reset', () => {
    const withUnread = textContent(
      ResidentWorkspaceSidebar({
        currentSessionId: 'build',
        onNew: () => {},
        onOpenAgents: () => {},
        onSelect: () => {},
        sessions,
        subagents: [],
        t: DEFAULT_THEME,
        unread: new Map([
          ['research', 3],
          ['build', -1]
        ])
      })
    )

    expect(withUnread).toContain('+3')
    expect(withUnread).toContain('•')
  })

  it('makes the composer target explicit', () => {
    const frame = textContent(
      ResidentInputTarget({ currentSessionId: 'build', sessions, t: DEFAULT_THEME })
    )

    expect(frame).toContain('To Build')
    // Switching hints live once, in the sidebar beside the session list.
    expect(frame).not.toContain('Ctrl+X')
  })

  it('renders a compact live pane for a background session', () => {
    const frame = textContent(
      ResidentSessionPreview({ index: 0, onSelect: () => {}, session: sessions[0]!, t: DEFAULT_THEME })
    )

    expect(frame).toContain('Research')
    expect(frame).toContain('gpt-5.6-luna')
    expect(frame).toContain('4 messages')
    expect(frame).toContain('Comparing provider pricing')
  })

  it('flags a waiting session with an explicit needs-input label', () => {
    const frame = textContent(
      ResidentSessionPreview({
        index: 0,
        onSelect: () => {},
        session: { ...sessions[0]!, status: 'waiting' },
        t: DEFAULT_THEME
      })
    )

    expect(frame).toContain('needs input')
  })
})
