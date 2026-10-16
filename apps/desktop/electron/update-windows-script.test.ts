import assert from 'node:assert/strict'

import { test } from 'vitest'

import { buildWindowsUpdateScript, psEscape } from './update-windows-script'

test('psEscape escapes backticks, dollars, and double quotes', () => {
  assert.equal(psEscape('simple'), 'simple')
  assert.equal(psEscape('hello $world'), 'hello `$world')
  assert.equal(psEscape('say "hi"'), 'say `"hi`"')
  assert.equal(psEscape('tick ` one'), 'tick `` one')
  assert.equal(psEscape('mix: "$`"'), 'mix: `"`$```"')
})

test('psEscape escapes typographic quotes PowerShell treats as string delimiters', () => {
  for (const quote of ['\u201C', '\u201D', '\u201E']) {
    assert.equal(psEscape(`a${quote}; calc; ${quote}b`), `a\`${quote}; calc; \`${quote}b`)
  }
})

test('buildWindowsUpdateScript claims the marker before waiting and cleans up after', () => {
  const script = buildWindowsUpdateScript({
    parentPid: 1,
    updateRoot: 'C:\\jettstui',
    jettstuiHome: 'C:\\jettstui-home',
    markerPath: 'C:\\jettstui-home\\.jettstui-update-in-progress'
  })

  const claim = script.indexOf('WriteAllText($markerPath')
  assert.ok(claim > 0 && claim < script.indexOf('WaitForExit'))
  assert.ok(script.includes('"$PID`n$startedAt`n"'))
  assert.ok(script.includes('Remove-Item -LiteralPath $PSCommandPath'))
})

test('psEscape handles Windows paths without escaping backslashes', () => {
  const winPath = 'C:\\Users\\raio\\AppData\\Local\\jettstui'
  assert.equal(psEscape(winPath), winPath)
})

test('buildWindowsUpdateScript generates script with options substituted', () => {
  const script = buildWindowsUpdateScript({
    parentPid: 12345,
    updateRoot: 'C:\\Users\\raio\\AppData\\Local\\jettstui\\jettstui',
    branch: 'main',
    execPath: 'C:\\Users\\raio\\AppData\\Local\\jettstui\\jettstui\\apps\\desktop\\release\\win-unpacked\\JettsTUI.exe',
    execArgs: ['--profile', 'work'],
    jettstuiHome: 'C:\\Users\\raio\\AppData\\Local\\jettstui',
    markerPath: 'C:\\Users\\raio\\AppData\\Local\\jettstui\\.jettstui-update-in-progress'
  })

  assert.ok(script.includes('$parentPid = 12345'))
  assert.ok(script.includes('$env:JETTSTUI_HOME = "C:\\Users\\raio\\AppData\\Local\\jettstui"'))
  assert.ok(script.includes('$updateRoot = "C:\\Users\\raio\\AppData\\Local\\jettstui\\jettstui"'))
  assert.ok(script.includes('$branch = "main"'))
  assert.ok(script.includes('JettsTUI.exe'))
  assert.ok(script.includes('--profile'))
  assert.ok(script.includes('.jettstui-update-in-progress'))
  assert.ok(script.includes('WaitForExit(30000)'))
  assert.ok(script.includes('update", "--yes", "--force", "--branch"'))
})

test('buildWindowsUpdateScript works with minimal options and default branch', () => {
  const script = buildWindowsUpdateScript({
    updateRoot: 'C:\\jettstui',
    jettstuiHome: 'C:\\jettstui-home'
  })

  assert.ok(script.includes('$branch = "main"'))
  assert.ok(script.includes('$parentPid = 0'))
  assert.ok(script.includes('$env:JETTSTUI_HOME = "C:\\jettstui-home"'))
})
