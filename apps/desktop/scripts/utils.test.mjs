import assert from 'node:assert/strict'
import { pathToFileURL } from 'node:url'
import { test } from 'vitest'

import { isMain } from './utils.mjs'

test('isMain handles embedded runtimes with no argv script', () => {
  const script = process.argv[1]
  try {
    process.argv[1] = undefined
    assert.equal(isMain('file:///example.mjs'), false)
  } finally {
    process.argv[1] = script
  }
})

test('isMain recognizes the invoked script', () => {
  const script = process.argv[1]
  try {
    process.argv[1] = 'example.mjs'
    assert.equal(isMain(pathToFileURL('example.mjs').href), true)
    assert.equal(isMain('file:///other.mjs'), false)
  } finally {
    process.argv[1] = script
  }
})
