import { describe, expect, it } from 'vitest'

import { cellAt, CellWidth, CharPool, createScreen, HyperlinkPool, setCellAt, StylePool } from './screen.js'
import {
  applySelectionOverlay,
  createSelectionState,
  findPlainTextUrlAt,
  getSelectedText,
  startSelection,
  updateSelection
} from './selection.js'

const screenWithText = () => {
  const styles = new StylePool()
  const screen = createScreen(10, 3, styles, new CharPool(), new HyperlinkPool())

  setCellAt(screen, 2, 1, { char: 'h', hyperlink: undefined, styleId: screen.emptyStyleId, width: CellWidth.Narrow })
  setCellAt(screen, 3, 1, { char: 'i', hyperlink: undefined, styleId: screen.emptyStyleId, width: CellWidth.Narrow })

  return { screen, styles }
}

describe('selection whitespace handling', () => {
  it('does not copy whitespace-only selections', () => {
    const { screen } = screenWithText()
    const selection = createSelectionState()

    startSelection(selection, 0, 0)
    updateSelection(selection, 9, 0)

    expect(getSelectedText(selection, screen)).toBe('')
  })

  it('trims outer drag padding while preserving selected content', () => {
    const { screen } = screenWithText()
    const selection = createSelectionState()

    startSelection(selection, 0, 1)
    updateSelection(selection, 9, 1)

    expect(getSelectedText(selection, screen)).toBe('hi')
  })

  it('preserves selected indentation when spaces are rendered content', () => {
    const styles = new StylePool()
    const screen = createScreen(10, 1, styles, new CharPool(), new HyperlinkPool())
    const selection = createSelectionState()

    setCellAt(screen, 0, 0, { char: ' ', hyperlink: undefined, styleId: screen.emptyStyleId, width: CellWidth.Narrow })
    setCellAt(screen, 1, 0, { char: ' ', hyperlink: undefined, styleId: screen.emptyStyleId, width: CellWidth.Narrow })
    setCellAt(screen, 2, 0, { char: 'x', hyperlink: undefined, styleId: screen.emptyStyleId, width: CellWidth.Narrow })

    startSelection(selection, 0, 0)
    updateSelection(selection, 9, 0)

    expect(getSelectedText(selection, screen)).toBe('  x')
  })

  it('clamps copied selection bounds to screen width', () => {
    const { screen } = screenWithText()
    const selection = createSelectionState()

    startSelection(selection, 0, 1)
    updateSelection(selection, 99, 1)

    expect(getSelectedText(selection, screen)).toBe('hi')
  })

  it('does not paint selection background on leading/trailing empty cells or empty rows', () => {
    const { screen, styles } = screenWithText()
    const selection = createSelectionState()

    startSelection(selection, 0, 0)
    updateSelection(selection, 9, 2)
    applySelectionOverlay(screen, selection, styles)

    expect(cellAt(screen, 0, 0)?.styleId).toBe(screen.emptyStyleId)
    expect(cellAt(screen, 0, 1)?.styleId).toBe(screen.emptyStyleId)
    expect(cellAt(screen, 2, 1)?.styleId).not.toBe(screen.emptyStyleId)
    expect(cellAt(screen, 4, 1)?.styleId).toBe(screen.emptyStyleId)
    expect(cellAt(screen, 0, 2)?.styleId).toBe(screen.emptyStyleId)
  })
})

describe('findPlainTextUrlAt', () => {
  const writeRow = (screen: any, row: number, startCol: number, text: string) => {
    for (let i = 0; i < text.length; i++) {
      setCellAt(screen, startCol + i, row, {
        char: text[i]!,
        hyperlink: undefined,
        styleId: screen.emptyStyleId,
        width: CellWidth.Narrow
      })
    }
  }

  it('detects a single-line URL at clicked column', () => {
    const styles = new StylePool()
    const screen = createScreen(30, 1, styles, new CharPool(), new HyperlinkPool())
    writeRow(screen, 0, 0, 'link: https://example.com/foo.')

    expect(findPlainTextUrlAt(screen, 10, 0)).toBe('https://example.com/foo')
  })

  it('detects a multi-line wrapped URL when clicking on the first line', () => {
    const styles = new StylePool()
    const screen = createScreen(20, 2, styles, new CharPool(), new HyperlinkPool())
    // 20 chars per row: "https://example.com/" (20 chars) wraps to "auth?client_id=123"
    writeRow(screen, 0, 0, 'https://example.com/')
    writeRow(screen, 1, 0, 'auth?client_id=123')

    expect(findPlainTextUrlAt(screen, 5, 0)).toBe('https://example.com/auth?client_id=123')
  })

  it('detects a multi-line wrapped URL when clicking on a continuation line', () => {
    const styles = new StylePool()
    const screen = createScreen(20, 3, styles, new CharPool(), new HyperlinkPool())
    writeRow(screen, 0, 0, 'https://example.com/')
    writeRow(screen, 1, 0, 'auth?code=xyz&state=')
    writeRow(screen, 2, 0, '12345')

    // Click on row 1 (the continuation without scheme)
    expect(findPlainTextUrlAt(screen, 5, 1)).toBe('https://example.com/auth?code=xyz&state=12345')
    // Click on row 2 (the final continuation line)
    expect(findPlainTextUrlAt(screen, 2, 2)).toBe('https://example.com/auth?code=xyz&state=12345')
  })
})
