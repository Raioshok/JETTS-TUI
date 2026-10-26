import { describe, expect, it } from 'vitest'

import { titlebarDragGaps } from './titlebar-drag'

const overlaps = (a: { left: number; right: number | null }, b: { left: number; right: number }) =>
  a.left < b.right && (a.right ?? Infinity) > b.left

describe('titlebarDragGaps', () => {
  it('never lets a drag strip overlap a control cluster', () => {
    const clusters = [
      { left: 526, right: 896 },
      { left: 14, right: 106 },
      { left: 1064, right: 1204 }
    ]

    const gaps = titlebarDragGaps(clusters)

    for (const gap of gaps) {
      for (const cluster of clusters) {
        expect(overlaps(gap, cluster)).toBe(false)
      }
    }

    // Everything between the clusters still drags, through to the band's end.
    expect(gaps).toHaveLength(4)
    expect(gaps.at(-1)?.right).toBeNull()
  })

  it('drags the whole band when no controls are mounted (overlay routes)', () => {
    expect(titlebarDragGaps([])).toEqual([{ left: 0, right: null }])
  })

  it('merges touching or overlapping clusters into one hole', () => {
    expect(titlebarDragGaps([{ left: 100, right: 200 }, { left: 202, right: 300 }], 4)).toEqual([
      { left: 0, right: 96 },
      { left: 304, right: null }
    ])
  })
})
