import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { test } from 'vitest'

import { electronDistVersion, matchesElectronDist } from './electron-dist-match.mjs'

test('only packages a local Electron dist whose binary and version match', () => {
  const dist = fs.mkdtempSync(path.join(os.tmpdir(), 'jetts-electron-dist-'))
  const binary = path.join(dist, 'electron.exe')
  try {
    fs.writeFileSync(binary, '')
    fs.writeFileSync(path.join(dist, 'version'), '40.10.2')
    assert.equal(matchesElectronDist(dist, binary, '41.10.7'), false)

    fs.writeFileSync(path.join(dist, 'version'), 'v41.10.7')
    assert.equal(electronDistVersion(dist), '41.10.7')
    assert.equal(matchesElectronDist(dist, binary, '41.10.7'), true)

    fs.rmSync(binary)
    assert.equal(matchesElectronDist(dist, binary, '41.10.7'), false)
  } finally {
    fs.rmSync(dist, { recursive: true, force: true })
  }
})
