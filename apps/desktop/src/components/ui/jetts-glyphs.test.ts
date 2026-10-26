import { describe, expect, it } from 'vitest'

import { JETTS_GLYPHS } from './jetts-glyphs'

describe('JETTS_GLYPHS', () => {
  it('every glyph is one path of plain SVG path commands that starts with a moveto', () => {
    for (const [name, d] of Object.entries(JETTS_GLYPHS)) {
      expect(d, name).toMatch(/^M[\d\s.,MmLlHhVvCcSsQqTtAaZz-]+$/)
    }
  })

  it('absolute coordinates stay inside the 24×24 grid', () => {
    for (const [name, d] of Object.entries(JETTS_GLYPHS)) {
      // Only absolute moveto/lineto pairs are checked; relative and arc args are deltas/radii.
      for (const [, x, y] of d.matchAll(/[ML]\s*(-?[\d.]+)[\s,]+(-?[\d.]+)/g)) {
        expect(Number(x), `${name} x`).toBeGreaterThanOrEqual(0)
        expect(Number(x), `${name} x`).toBeLessThanOrEqual(24)
        expect(Number(y), `${name} y`).toBeGreaterThanOrEqual(0)
        expect(Number(y), `${name} y`).toBeLessThanOrEqual(24)
      }
    }
  })
})
