import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { afterEach, describe, expect, it } from 'vitest'

import { managedCheckoutRoot, migrateDefaultHome } from './home-migration'

const roots: string[] = []

function paths() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'jetts-home-test-'))
  roots.push(root)
  return { old: path.join(root, 'freeide'), branded: path.join(root, 'jettstui') }
}

afterEach(() => {
  for (const root of roots.splice(0)) {
    fs.rmSync(root, { recursive: true, force: true })
  }
})

describe('default home migration', () => {
  it('moves existing data while keeping the old launcher path usable', () => {
    const { old, branded } = paths()
    fs.mkdirSync(old)
    fs.writeFileSync(path.join(old, 'state.db'), 'sessions')

    expect(migrateDefaultHome(branded, old)).toBe(branded)
    expect(fs.readFileSync(path.join(branded, 'state.db'), 'utf8')).toBe('sessions')
    expect(fs.readFileSync(path.join(old, 'state.db'), 'utf8')).toBe('sessions')
  })

  it('never merges into an existing destination', () => {
    const { old, branded } = paths()
    fs.mkdirSync(old)
    fs.mkdirSync(branded)
    fs.writeFileSync(path.join(old, 'config.yaml'), 'old')
    fs.writeFileSync(path.join(branded, 'config.yaml'), 'new')

    expect(migrateDefaultHome(branded, old)).toBe(branded)
    expect(fs.readFileSync(path.join(old, 'config.yaml'), 'utf8')).toBe('old')
    expect(fs.readFileSync(path.join(branded, 'config.yaml'), 'utf8')).toBe('new')
  })
})

describe('managed checkout resolution', () => {
  it('uses the branded path for a fresh install', () => {
    const { branded } = paths()
    expect(managedCheckoutRoot(path.dirname(branded))).toBe(branded)
  })

  it('keeps an existing legacy Git checkout', () => {
    const { old } = paths()
    const home = path.dirname(old)
    const legacy = path.join(home, 'freeide-agent')
    fs.mkdirSync(path.join(legacy, '.git'), { recursive: true })
    expect(managedCheckoutRoot(home)).toBe(legacy)
  })

  it('prefers a branded Git checkout when both paths exist', () => {
    const { branded } = paths()
    const home = path.dirname(branded)
    fs.mkdirSync(path.join(home, 'freeide-agent', '.git'), { recursive: true })
    fs.mkdirSync(path.join(branded, '.git'), { recursive: true })
    expect(managedCheckoutRoot(home)).toBe(branded)
  })

  it('does not mistake a worktree .git file for an installer-managed checkout', () => {
    const { branded } = paths()
    const home = path.dirname(branded)
    fs.mkdirSync(branded)
    fs.writeFileSync(path.join(branded, '.git'), 'gitdir: elsewhere')
    const legacy = path.join(home, 'freeide-agent')
    fs.mkdirSync(path.join(legacy, '.git'), { recursive: true })
    expect(managedCheckoutRoot(home)).toBe(legacy)
  })
})
