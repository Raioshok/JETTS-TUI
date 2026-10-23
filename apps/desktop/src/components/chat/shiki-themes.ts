/**
 * Skin-specific syntax themes for the file source view.
 *
 * Shiki themes are fixed palettes, so a skin that wants its own token colors
 * ships a TextMate theme object here; every other skin keeps the
 * caller's default pair. Pure data + a pure picker — no React, no shiki import.
 */

interface TokenRule {
  scope: string[]
  settings: { fontStyle?: string; foreground?: string }
}

export interface SyntaxTheme {
  colors: Record<string, string>
  name: string
  tokenColors: TokenRule[]
  type: 'dark' | 'light'
}

interface Palette {
  comment: string
  constant: string
  foreground: string
  keyword: string
  punctuation: string
  string: string
  type: string
}

function syntaxTheme(name: string, type: 'dark' | 'light', p: Palette): SyntaxTheme {
  return {
    name,
    type,
    colors: { 'editor.foreground': p.foreground },
    tokenColors: [
      {
        scope: ['comment', 'punctuation.definition.comment'],
        settings: { fontStyle: 'italic', foreground: p.comment }
      },
      {
        scope: ['keyword', 'storage', 'storage.type', 'storage.modifier', 'keyword.operator.new', 'variable.language'],
        settings: { foreground: p.keyword }
      },
      { scope: ['string', 'string.template', 'punctuation.definition.string'], settings: { foreground: p.string } },
      { scope: ['constant.numeric', 'constant.language', 'constant.character'], settings: { foreground: p.constant } },
      {
        scope: [
          'entity.name.type',
          'entity.name.class',
          'support.type',
          'support.class',
          'entity.other.inherited-class'
        ],
        settings: { foreground: p.type }
      },
      {
        scope: ['entity.name.function', 'support.function', 'meta.function-call'],
        settings: { foreground: p.foreground }
      },
      { scope: ['variable', 'variable.other', 'meta.object-literal.key'], settings: { foreground: p.foreground } },
      { scope: ['punctuation', 'meta.brace'], settings: { foreground: p.punctuation } },
      { scope: ['entity.name.tag'], settings: { foreground: p.keyword } },
      { scope: ['entity.other.attribute-name'], settings: { foreground: p.type } },
      { scope: ['markup.heading'], settings: { fontStyle: 'bold', foreground: p.keyword } }
    ]
  }
}

/** Ivory: orange keywords, gold strings/numbers, teal types on warm ink. */
export const IVORY_SYNTAX = {
  light: syntaxTheme('jettstui-ivory-light', 'light', {
    comment: '#9A948A',
    constant: '#B07D18',
    foreground: '#2B2925',
    keyword: '#C2692A',
    punctuation: '#5E5A53',
    string: '#A9791C',
    type: '#2F7FA3'
  }),
  dark: syntaxTheme('jettstui-ivory-dark', 'dark', {
    comment: '#7D776D',
    constant: '#E0B45C',
    foreground: '#E8E3DA',
    keyword: '#EE9A5E',
    punctuation: '#B5AEA2',
    string: '#D9B15E',
    type: '#6FB3D2'
  })
} as const

const SKIN_SYNTAX: Record<string, { dark: SyntaxTheme; light: SyntaxTheme }> = {
  ivory: IVORY_SYNTAX
}

/** The skin's own light/dark syntax pair, or undefined to keep the caller's default. */
export function skinSyntaxTheme(skin: string): { dark: SyntaxTheme; light: SyntaxTheme } | undefined {
  return SKIN_SYNTAX[skin]
}
