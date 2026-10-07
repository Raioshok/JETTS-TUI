import React from 'react'
import { describe, expect, it } from 'vitest'

import { ComposerToolbar, WorkspaceHeader } from '../components/workspaceChrome.js'
import { DEFAULT_THEME } from '../theme.js'

const textContent = (node: React.ReactNode): string => {
  if (node === null || node === undefined || typeof node === 'boolean') {
    return ''
  }

  if (typeof node === 'string' || typeof node === 'number') {
    return String(node)
  }

  if (Array.isArray(node)) {
    return node.map(textContent).join('')
  }

  return React.isValidElement(node) ? textContent(node.props.children) : ''
}

describe('WorkspaceHeader responsive hierarchy', () => {
  const base = {
    brand: 'JettsTUI',
    busy: false,
    cwd: 'C:\\dev\\jettstui',
    mode: 'default' as const,
    model: 'openai/gpt-5.6-sol',
    project: 'jettstui',
    t: DEFAULT_THEME
  }

  it('shows model and mode when there is room', () => {
    const frame = textContent(WorkspaceHeader({ ...base, cols: 100 }))

    expect(frame).toContain('JettsTUI')
    expect(frame).toContain('jettstui')
    expect(frame).toContain('gpt 5.6 sol')
    expect(frame).toContain('DEFAULT')
  })

  it('keeps identity while progressively hiding secondary context', () => {
    const frame = textContent(WorkspaceHeader({ ...base, cols: 36 }))

    expect(frame).toContain('JettsTUI')
    expect(frame).not.toContain('gpt 5.6 sol')
    expect(frame).not.toContain('DEFAULT')
  })

  it('reflects active work and plan mode without changing layout structure', () => {
    const frame = textContent(WorkspaceHeader({ ...base, busy: true, cols: 80, mode: 'plan' }))

    expect(frame).toContain('◆')
    expect(frame).toContain('PLAN')
  })
})

describe('ComposerToolbar disclosure', () => {
  it('teaches the full keyboard workflow on wide terminals', () => {
    const frame = textContent(
      ComposerToolbar({ busy: false, cols: 100, mode: 'accept-edits', queueCount: 0, t: DEFAULT_THEME })
    )

    expect(frame).toContain('NEW MESSAGE')
    expect(frame).toContain('Enter send')
    expect(frame).toContain('Shift+Enter newline')
    expect(frame).toContain('Shift+Tab mode')
  })

  it('prioritizes state over hotkey help when space is tight', () => {
    const frame = textContent(ComposerToolbar({ busy: true, cols: 34, mode: 'plan', queueCount: 2, t: DEFAULT_THEME }))

    expect(frame).toContain('STEER AGENT')
    expect(frame).toContain('PLAN')
    expect(frame).not.toContain('Shift+Enter')
  })

  it('surfaces queued work while idle', () => {
    const frame = textContent(
      ComposerToolbar({ busy: false, cols: 60, mode: 'default', queueCount: 3, t: DEFAULT_THEME })
    )

    expect(frame).toContain('3 QUEUED')
  })

  it('uses a compact state label instead of overflowing tiny terminals', () => {
    const frame = textContent(
      ComposerToolbar({ busy: false, cols: 18, mode: 'default', queueCount: 0, t: DEFAULT_THEME })
    )

    expect(frame).toContain('MESSAGE')
    expect(frame).not.toContain('NEW MESSAGE')
    expect(frame).not.toContain('Enter send')
  })
})
