import { render } from '@testing-library/react'
import { createElement } from 'react'
import { describe, expect, it } from 'vitest'

import * as icons from './icons'
import { jettsIcon } from './jetts-icon'

const components = Object.entries(icons)
  .filter(([, value]) => typeof value === 'function' || typeof value === 'object')
  .filter(([name]) => name !== 'iconSize') as [string, React.ComponentType<Record<string, unknown>>][]

describe('lib/icons', () => {
  it('every exported icon renders a 24-grid svg with a drawn path', () => {
    for (const [name, Component] of components) {
      const { container, unmount } = render(createElement(Component))
      const svg = container.querySelector('svg')

      expect(svg, name).not.toBeNull()
      expect(svg?.getAttribute('viewBox'), name).toBe('0 0 24 24')
      expect(svg?.querySelector('path')?.getAttribute('d'), name).toBeTruthy()
      unmount()
    }
  })
})

describe('jettsIcon', () => {
  it('honours the Tabler props call sites pass', () => {
    const Plus = jettsIcon('add')
    const { container } = render(createElement(Plus, { className: 'size-4', size: 16, stroke: 2, title: 'Add' }))
    const svg = container.querySelector('svg')!

    expect(svg.getAttribute('width')).toBe('16')
    expect(svg.getAttribute('stroke-width')).toBe('2')
    expect(svg.classList.contains('tabler-icon')).toBe(true)
    expect(svg.classList.contains('size-4')).toBe(true)
    expect(svg.querySelector('title')?.textContent).toBe('Add')
  })

  it('fills only the filled variants', () => {
    const outline = render(createElement(jettsIcon('zap'))).container.querySelector('svg')!
    const filled = render(createElement(jettsIcon('zap', { filled: true }))).container.querySelector('svg')!

    expect(outline.getAttribute('fill')).toBe('none')
    expect(filled.getAttribute('fill')).toBe('currentColor')
  })

  it('fails loudly on an unknown glyph instead of rendering blank', () => {
    expect(() => jettsIcon('no-such-glyph')).toThrow(/no-such-glyph/)
  })
})
