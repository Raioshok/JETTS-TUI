/**
 * Tests for electron/update-relaunch.ts — the pure decision + script helpers
 * behind the Linux in-app update relaunch (#45205).
 *
 * Run with: node --test electron/update-relaunch.test.ts
 * (Wired into npm test:desktop:platforms in package.json.)
 *
 * What this locks (review acceptance criteria for PR #45205):
 *   1. The execPath split: only a binary under release/<plat>-unpacked may
 *      relaunch/claim a GUI update; AppImage/.deb/.rpm/dev/unresolved paths land
 *      on the guiSkew terminal state and do NOT claim the GUI was updated.
 *   2. Launch context is replayed on re-exec (args filtered of Electron
 *      internals; FREEIDE_HOME / FREEIDE_DESKTOP_* env + cwd preserved) and is
 *      safely shell-quoted.
 *   3. The sandbox preflight: chrome-sandbox must be root-owned + setuid to be
 *      launchable; otherwise the decision degrades to a manual terminal state
 *      (keep a working window) unless a non-interactive fallback applies.
 */

import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { test } from 'vitest'

import {
  buildRelaunchScript,
  collectRelaunchArgs,
  collectRelaunchEnv,
  decideRelaunchOutcome,
  resolveUnpackedRelease,
  sandboxFallbackFromEnv,
  sandboxPreflight,
  shellQuote,
  unpackedDirName
} from './update-relaunch'

// resolveUnpackedRelease uses the host path module, so fixtures need a native
// absolute root even when exercising its Linux release-directory contract.
const ROOT = path.resolve(os.tmpdir(), 'jetts-tui-update-relaunch-fixture')
const UNPACKED = path.join(ROOT, 'apps', 'desktop', 'release', 'linux-unpacked')
const BASH = process.platform === 'win32'
  ? path.join(process.env.ProgramFiles || 'C:\\Program Files', 'Git', 'bin', 'bash.exe')
  : 'bash'

// ---------------------------------------------------------------------------
// 1) The execPath split — the heart of the GUI/backend skew guard.
// ---------------------------------------------------------------------------

test('unpackedDirName maps platform to the electron-builder dir', () => {
  assert.equal(unpackedDirName('linux'), 'linux-unpacked')
  assert.equal(unpackedDirName('win32'), 'win-unpacked')
})

test('resolveUnpackedRelease returns the dir for a binary UNDER release/<plat>-unpacked', () => {
  const exec = path.join(UNPACKED, 'freeide')
  assert.equal(resolveUnpackedRelease(exec, ROOT, 'linux'), UNPACKED)
  // The unpacked dir itself also counts.
  assert.equal(resolveUnpackedRelease(UNPACKED, ROOT, 'linux'), UNPACKED)
})

test('resolveUnpackedRelease is null for AppImage / .deb / .rpm / dev / unresolved paths', () => {
  // AppImage mount
  assert.equal(resolveUnpackedRelease('/tmp/.mount_FreeIDE12345/AppRun', ROOT, 'linux'), null)
  // .deb / .rpm system install
  assert.equal(resolveUnpackedRelease('/usr/lib/freeide/freeide', ROOT, 'linux'), null)
  assert.equal(resolveUnpackedRelease('/opt/FreeIDE/freeide', ROOT, 'linux'), null)
  // dev electron
  assert.equal(
    resolveUnpackedRelease('/home/u/.freeide/freeide-agent/node_modules/electron/dist/electron', ROOT, 'linux'),
    null
  )
  // empty / missing
  assert.equal(resolveUnpackedRelease('', ROOT, 'linux'), null)
  assert.equal(resolveUnpackedRelease(path.join(UNPACKED, 'freeide'), '', 'linux'), null)
})

test('resolveUnpackedRelease is not fooled by a sibling prefix dir', () => {
  // `.../release/linux-unpacked-evil` must NOT match `.../release/linux-unpacked`.
  const sneaky = path.join(ROOT, 'apps', 'desktop', 'release', 'linux-unpacked-evil', 'freeide')
  assert.equal(resolveUnpackedRelease(sneaky, ROOT, 'linux'), null)
})

test('decideRelaunchOutcome: only under-unpacked + sandbox-ok relaunches', () => {
  assert.equal(decideRelaunchOutcome({ underUnpacked: true, sandboxOk: true }), 'relaunch')
  // Under unpacked but sandbox not launchable → manual (keep a working window).
  assert.equal(decideRelaunchOutcome({ underUnpacked: true, sandboxOk: false }), 'manual')
  // Not under unpacked → guiSkew regardless of sandbox flag.
  assert.equal(decideRelaunchOutcome({ underUnpacked: false, sandboxOk: true }), 'guiSkew')
  assert.equal(decideRelaunchOutcome({ underUnpacked: false, sandboxOk: false }), 'guiSkew')
})

// ---------------------------------------------------------------------------
// 3) Sandbox preflight
// ---------------------------------------------------------------------------

const fakeStat = (uid, mode) => () => ({ uid, mode })

const throwStat = () => {
  throw Object.assign(new Error('ENOENT'), { code: 'ENOENT' })
}

test('sandboxPreflight: root-owned + setuid is launchable', () => {
  const r = sandboxPreflight(UNPACKED, fakeStat(0, 0o4755))
  assert.equal(r.ok, true)
  assert.equal(r.reason, 'launchable')
})

test('sandboxPreflight: not root → not launchable', () => {
  const r = sandboxPreflight(UNPACKED, fakeStat(1000, 0o4755))
  assert.equal(r.ok, false)
  assert.equal(r.reason, 'not-root')
})

test('sandboxPreflight: missing setuid bit → not launchable', () => {
  const r = sandboxPreflight(UNPACKED, fakeStat(0, 0o755))
  assert.equal(r.ok, false)
  assert.equal(r.reason, 'not-setuid')
})

test('sandboxPreflight: neither root nor setuid (the fresh-rebuild trap)', () => {
  const r = sandboxPreflight(UNPACKED, fakeStat(1000, 0o755))
  assert.equal(r.ok, false)
  assert.equal(r.reason, 'not-root-not-setuid')
})

test('sandboxPreflight: no chrome-sandbox helper present → ok (build does not use SUID sandbox)', () => {
  const r = sandboxPreflight(UNPACKED, throwStat)
  assert.equal(r.ok, true)
  assert.equal(r.reason, 'no-sandbox-helper')
})

test('sandboxFallbackFromEnv: ELECTRON_DISABLE_SANDBOX / --no-sandbox make a broken sandbox safe', () => {
  assert.equal(sandboxFallbackFromEnv({ ELECTRON_DISABLE_SANDBOX: '1' }, []), true)
  assert.equal(sandboxFallbackFromEnv({ ELECTRON_DISABLE_SANDBOX: 'true' }, []), true)
  assert.equal(sandboxFallbackFromEnv({}, ['--no-sandbox']), true)
  assert.equal(sandboxFallbackFromEnv({}, ['--foo']), false)
  assert.equal(sandboxFallbackFromEnv({}, []), false)
  assert.equal(sandboxFallbackFromEnv(null, null), false)
})

// ---------------------------------------------------------------------------
// 2) Launch-context preservation
// ---------------------------------------------------------------------------

test('collectRelaunchArgs drops Electron internals, keeps user/launcher args', () => {
  const argv = [
    '--type=renderer',
    '--user-data-dir=/tmp/x',
    '--enable-features=Foo',
    '--field-trial-handle=123',
    '--no-sandbox', // sandbox opt-out — KEEP (user/env intent + relaunch fallback)
    '--lang=en-US',
    'freeide://open/agent/42', // deep link — keep
    '--profile=work', // app flag — keep
    '--remote-debugging-port=9222' // internal — drop
  ]

  assert.deepEqual(collectRelaunchArgs(argv), ['--no-sandbox', 'freeide://open/agent/42', '--profile=work'])
  assert.deepEqual(collectRelaunchArgs(undefined), [])
})

test('collectRelaunchEnv preserves FREEIDE_HOME + FREEIDE_DESKTOP_* + sandbox opt-out only', () => {
  const env = {
    FREEIDE_HOME: '/home/u/.freeide',
    FREEIDE_DESKTOP_REMOTE_URL: 'http://box:9119',
    FREEIDE_DESKTOP_REMOTE_TOKEN: 'secret',
    FREEIDE_DESKTOP_FREEIDE_ROOT: '/home/u/dev/freeide',
    FREEIDE_DESKTOP_APP_NAME: 'FreeIDESandbox',
    ELECTRON_DISABLE_SANDBOX: '1', // sandbox opt-out — preserved
    PATH: '/usr/bin', // not preserved
    HOME: '/home/u', // not preserved
    UNRELATED: 'x'
  }

  assert.deepEqual(collectRelaunchEnv(env), {
    FREEIDE_HOME: '/home/u/.freeide',
    FREEIDE_DESKTOP_REMOTE_URL: 'http://box:9119',
    FREEIDE_DESKTOP_REMOTE_TOKEN: 'secret',
    FREEIDE_DESKTOP_FREEIDE_ROOT: '/home/u/dev/freeide',
    FREEIDE_DESKTOP_APP_NAME: 'FreeIDESandbox',
    ELECTRON_DISABLE_SANDBOX: '1'
  })
  assert.deepEqual(collectRelaunchEnv(null), {})
})

// ---------------------------------------------------------------------------
// Generated watcher script: safe quoting + valid bash syntax.
// ---------------------------------------------------------------------------

test('shellQuote neutralizes single quotes and metacharacters', () => {
  assert.equal(shellQuote(`a'b`), `'a'\\''b'`)
  assert.equal(shellQuote('$(rm -rf /)'), `'$(rm -rf /)'`)
})

test.skipIf(process.platform === 'win32' && !fs.existsSync(BASH))('buildRelaunchScript embeds pid/exec/args/env/cwd and is valid bash', () => {
  const script = buildRelaunchScript({
    pid: 4242,
    execPath: '/home/u/.freeide/freeide-agent/apps/desktop/release/linux-unpacked/FreeIDE',
    args: ['freeide://open/agent/42', "--note=it's fine"],
    env: { FREEIDE_HOME: '/home/u/.freeide', FREEIDE_DESKTOP_REMOTE_URL: 'http://box:9119' },
    cwd: '/home/u/work dir'
  })

  // Structural assertions.
  assert.match(script, /^#!\/bin\/bash/)
  assert.match(script, /APP_PID=4242/)
  assert.match(script, /kill -9 "\$APP_PID"/)
  assert.match(script, /rm -f -- "\$0"/)
  // env exports + cwd restore + args replay are present and quoted.
  assert.match(script, /export FREEIDE_HOME='\/home\/u\/\.freeide'/)
  assert.match(script, /export FREEIDE_DESKTOP_REMOTE_URL='http:\/\/box:9119'/)
  assert.match(script, /cd '\/home\/u\/work dir'/)
  assert.match(script, /exec '.*\/linux-unpacked\/FreeIDE' 'freeide:\/\/open\/agent\/42' '--note=it'\\''s fine'/)

  // Lint via stdin so a native Windows path need not be translated for Bash.
  execFileSync(BASH, ['-n'], { input: script, stdio: 'pipe' })
})

test.skipIf(process.platform === 'win32' && !fs.existsSync(BASH))('buildRelaunchScript with no args/env still lints clean', () => {
  const script = buildRelaunchScript({
    pid: 1,
    execPath: '/opt/FreeIDE/FreeIDE',
    args: [],
    env: {},
    cwd: ''
  })

  execFileSync(BASH, ['-n'], { input: script, stdio: 'pipe' })

  // exec line has no trailing args.
  assert.match(script, /exec '\/opt\/FreeIDE\/FreeIDE'\n/)
})
