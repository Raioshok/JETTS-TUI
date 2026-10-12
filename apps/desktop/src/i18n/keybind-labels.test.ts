import { describe, expect, it } from 'vitest'

import { TRANSLATIONS } from './catalog'

// `keybinds.actions` is a loose Record, so the type checker can't catch a
// locale that misses one; the keybind settings then show the raw action id
// (e.g. "view.newTerminal") as the label.
describe('keybind action labels', () => {
  const englishIds = Object.keys(TRANSLATIONS.en.keybinds.actions)

  it.each(Object.keys(TRANSLATIONS))('%s labels every keybind action', locale => {
    const labels = TRANSLATIONS[locale as keyof typeof TRANSLATIONS].keybinds.actions
    const missing = englishIds.filter(id => !labels[id]?.trim())

    expect(missing).toEqual([])
  })
})
