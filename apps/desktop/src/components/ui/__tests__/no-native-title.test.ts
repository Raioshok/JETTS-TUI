import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

// Static-analysis guard: no <button> or <Button> element in the desktop renderer
// may use the native HTML `title=` attribute. Native tooltips are unstyled,
// delayed (~500ms OS default), and visually inconsistent with the themed `Tip`.
// When a tip is warranted (see DESIGN.md — not every icon, never menu triggers),
// use `<Tip label={...}>` instead of `title=`.
//
// This is a source-text scan, not a behavior test — it's the same category as
// an ESLint rule, expressed as a vitest so it runs with the rest of the suite.

function collectTsxFiles(dir: string): string[] {
  const results: string[] = []

  for (const entry of readdirSync(dir)) {
    if (entry === 'node_modules' || entry === 'dist' || entry === '__tests__') {
      continue
    }

    const fullPath = join(dir, entry)
    const stat = statSync(fullPath)

    if (stat.isDirectory()) {
      results.push(...collectTsxFiles(fullPath))
    } else if (entry.endsWith('.tsx')) {
      results.push(fullPath)
    }
  }

  return results
}

function advancePastCommentOrString(
  src: string,
  index: number,
  quote: string | null
): { next: number; quote: string | null } {
  const ch = src[index]
  const nextCh = src[index + 1]

  if (quote) {
    if (ch === '\\') {
      return { next: index + 2, quote }
    }

    if (ch === quote) {
      return { next: index + 1, quote: null }
    }

    return { next: index + 1, quote }
  }

  if (ch === '/' && nextCh === '/') {
    const nl = src.indexOf('\n', index + 2)

    return { next: nl === -1 ? src.length : nl + 1, quote: null }
  }

  if (ch === '/' && nextCh === '*') {
    const end = src.indexOf('*/', index + 2)

    return { next: end === -1 ? src.length : end + 2, quote: null }
  }

  if (ch === '"' || ch === "'" || ch === '`') {
    return { next: index + 1, quote: ch }
  }

  return { next: index, quote: null }
}

function findButtonTagsWithTitle(content: string): { lineNum: number; tagName: string }[] {
  const hits: { lineNum: number; tagName: string }[] = []
  const startPattern = /<(Button|button)\b/gu
  let match: RegExpExecArray | null

  while ((match = startPattern.exec(content)) !== null) {
    const tagName = match[1]
    const attrStart = match.index + match[0].length
    let i = attrStart
    let braceDepth = 0
    let quote: string | null = null
    let hasTitle = false

    while (i < content.length) {
      const skipped = advancePastCommentOrString(content, i, quote)

      if (skipped.next !== i) {
        i = skipped.next
        quote = skipped.quote

        continue
      }

      const ch = content[i]

      if (ch === '{') {
        braceDepth++
        i++

        continue
      }

      if (ch === '}') {
        if (braceDepth > 0) {
          braceDepth--
        }

        i++

        continue
      }

      if (braceDepth === 0) {
        if (ch === '>') {
          break
        }

        const prev = i === attrStart ? ' ' : content[i - 1]

        if (/\s/.test(prev) && content.slice(i, i + 6) === 'title=') {
          hasTitle = true
        }
      }

      i++
    }

    if (hasTitle) {
      const lineNum = content.slice(0, match.index).split('\n').length
      hits.push({ lineNum, tagName })
    }
  }

  return hits
}

describe('no native title= on button elements', () => {
  it('uses <Tip> instead of native title= on all button elements', () => {
    const violations: string[] = []
    const srcDir = resolve(__dirname, '../..')

    for (const filePath of collectTsxFiles(srcDir)) {
      const content = readFileSync(filePath, 'utf-8')
      const relativePath = filePath.slice(srcDir.length + 1).replace(/\\/g, '/')

      for (const hit of findButtonTagsWithTitle(content)) {
        violations.push(`${relativePath}:${hit.lineNum} <${hit.tagName}> has title= — use <Tip>`)
      }
    }

    expect(violations, violations.join('\n')).toEqual([])
  })
})
