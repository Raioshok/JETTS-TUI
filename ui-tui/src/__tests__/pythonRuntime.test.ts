import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'

import { afterEach, expect, it } from 'vitest'

import { resolvePython } from '../gatewayClient.js'

const savedPython = process.env.PYTHON
const savedFreeidePython = process.env.FREEIDE_PYTHON
const savedVirtualEnv = process.env.VIRTUAL_ENV

afterEach(() => {
  if (savedPython === undefined) {
    delete process.env.PYTHON
  } else {
    process.env.PYTHON = savedPython
  }

  if (savedFreeidePython === undefined) {
    delete process.env.FREEIDE_PYTHON
  } else {
    process.env.FREEIDE_PYTHON = savedFreeidePython
  }

  if (savedVirtualEnv === undefined) {
    delete process.env.VIRTUAL_ENV
  } else {
    process.env.VIRTUAL_ENV = savedVirtualEnv
  }
})

it('finds a Windows virtualenv Python in a source checkout', () => {
  const root = mkdtempSync(join(tmpdir(), 'jetts-tui-python-'))
  const python = join(root, '.venv', 'Scripts', 'python.exe')
  delete process.env.PYTHON
  delete process.env.FREEIDE_PYTHON
  delete process.env.VIRTUAL_ENV

  try {
    mkdirSync(dirname(python), { recursive: true })
    writeFileSync(python, '')
    expect(resolvePython(root)).toBe(python)
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})
