import { describe, expect, it } from 'vitest'

import { findGroupOfPane, group, inheritMinimized, split } from './model'

describe('inheritMinimized', () => {
  const previous = split('row', [
    group(['workspace']),
    split('column', [group(['files']), group(['terminal', 'logs'], { minimized: true })], [1, 1])
  ])

  it('keeps a collapsed zone collapsed wherever its pane moved', () => {
    const next = split('column', [split('row', [group(['files']), group(['workspace'])]), group(['terminal'])], [3, 1])

    expect(findGroupOfPane(inheritMinimized(next, previous), 'terminal')?.minimized).toBe(true)
  })

  it('does not collapse zones that were open, nor touch panes it never saw', () => {
    const next = split('row', [group(['files'], { minimized: true }), group(['workspace']), group(['review'])])
    const result = inheritMinimized(next, previous)

    expect(findGroupOfPane(result, 'files')?.minimized).toBeFalsy()
    expect(findGroupOfPane(result, 'workspace')?.minimized).toBeFalsy()
    expect(findGroupOfPane(result, 'review')).toEqual(findGroupOfPane(next, 'review'))
  })
})
