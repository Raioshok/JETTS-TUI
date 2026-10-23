/**
 * End-to-end smoke test for the real terminal UI (`jettstui --tui`).
 *
 * Drives the shipped TUI inside a pseudo-terminal against the desktop e2e mock
 * inference server, and asserts on the raw ANSI the TUI paints:
 *
 *   - it boots and renders its chrome (status line with the model name)
 *   - it emits ANSI color codes (not a mono/plain fallback)
 *   - typing lands in the composer
 *   - submitting runs a turn, the reply renders, and the turn-complete marker
 *     appears
 *   - the chrome stays intact before / during / after the run — no corruption,
 *     no stack trace, no vanished status line
 *   - no palette flash on a cold start: the first frame (painted before the
 *     gateway skin arrives) uses only colors the settled theme also uses
 *   - multi-agent while busy: Ctrl+X → typing starts a second agent, the busy
 *     one is not offered twice, and switching back shows its turn once
 *
 * Standalone (not a vitest unit): it needs node-pty, a Python backend, the
 * built ink bundle and ~30s. Run with `npm run test:e2e` from ui-tui.
 */
import { spawn as ptySpawn } from 'node-pty'
import { strict as assert } from 'node:assert'
import * as fs from 'node:fs'
import * as os from 'node:os'
import * as path from 'node:path'

import { MOCK_REPLY, startMockServer } from '../../apps/desktop/e2e/mock-server.ts'

const REPO = path.resolve(import.meta.dirname, '..', '..')
const TSX = path.join(REPO, 'node_modules/tsx/dist/cli.mjs')
const ENTRY = path.join(REPO, 'ui-tui/src/entry.tsx')
const PY =
  process.env.JETTSTUI_PYTHON ||
  [path.join(REPO, '.venv/Scripts/python.exe'), path.join(REPO, '.venv/bin/python'), path.join(REPO, 'venv/bin/python')].find(
    p => fs.existsSync(p)
  ) ||
  (process.platform === 'win32' ? 'python' : 'python3')

const CSI = /\u001b\[[0-9;?]*[A-Za-z]/g
const OSC = /\u001b\][0-9]*;[^\u0007]*\u0007/g
const plain = (s: string) => s.replace(OSC, '').replace(CSI, '').replace(/\u001b[>=()][AB0]?/g, '')
const hasSgrColor = (s: string) => /\u001b\[[0-9;]*m/.test(s)
// Foreground-only SGR color codes: a theme flash is text painted in another
// palette. Background chips are skipped — some only exist during boot (the
// composer's placeholder cursor chip), so they have nothing to match later.
const sgrColors = (s: string) =>
  new Set(
    [...s.matchAll(/\u001b\[([0-9;]*)m/g)]
      .map(m => m[1])
      .filter(code => code && code !== '0' && !code.split(';').some(p => /^(4\d|10\d)$/.test(p)))
  )
const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))

function writeConfig(home: string, mockUrl: string): void {
  fs.writeFileSync(
    path.join(home, 'config.yaml'),
    [
      'model:',
      '  default: mock-model',
      '  provider: mock',
      'providers:',
      '  mock:',
      `    api: ${mockUrl}/v1`,
      '    name: Mock',
      '    api_mode: chat_completions',
      '    key_env: MOCK_API_KEY',
      '    models:',
      '      mock-model: {}',
      '    context_length: 4096',
      ''
    ].join('\n')
  )
  fs.writeFileSync(path.join(home, '.env'), 'MOCK_API_KEY=e2e-mock-key\n')
}

async function waitFor(get: () => string, predicate: (s: string) => boolean, timeoutMs: number, label: string): Promise<void> {
  const until = Date.now() + timeoutMs

  while (Date.now() < until) {
    if (predicate(get())) {
      return
    }

    await sleep(250)
  }

  const tail = plain(get()).split('\n').filter(l => l.trim()).slice(-20).join('\n')
  throw new Error(`timed out waiting for: ${label}\n--- recent screen ---\n${tail}`)
}

async function main(): Promise<void> {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'jettstui-tui-e2e-'))
  const mock = await startMockServer()
  writeConfig(home, mock.url)

  let buf = ''
  const term = ptySpawn(process.execPath, [TSX, ENTRY], {
    name: 'xterm-256color',
    cols: 100,
    rows: 30,
    cwd: path.join(REPO, 'ui-tui'),
    // ConPTY's console-list helper breaks under tsx on Windows; winpty is fine.
    useConpty: false,
    env: {
      ...process.env,
      JETTSTUI_HOME: home,
      JETTSTUI_PYTHON: PY,
      TERM: 'xterm-256color',
      COLORTERM: 'truecolor',
      FORCE_COLOR: '3',
      JETTSTUI_TUI: '1'
    }
  } as Parameters<typeof ptySpawn>[2])
  term.onData(d => {
    buf += d
  })

  const cleanup = async () => {
    try {
      term.kill()
    } catch {
      /* already gone */
    }

    await mock.close().catch(() => undefined)

    try {
      fs.rmSync(home, { recursive: true, force: true })
    } catch {
      /* best effort */
    }
  }

  try {
    // 1. Boots and paints its chrome. The status line names the model.
    await waitFor(() => buf, s => plain(s).includes('mock model') && plain(s).includes('session'), 30_000, 'TUI boot (status line with model)')
    const firstFrame = buf

    // No palette flash: once the gateway skin has landed, force a full repaint
    // (resize) and require every color of the first frame to still be in use.
    // A skinless palette that disagrees with the default skin shows up here.
    await waitFor(() => buf, s => plain(s).includes('ready'), 30_000, 'session ready (skin applied)')
    await sleep(1500)
    const beforeRepaint = buf.length
    term.resize(101, 30)
    await sleep(1500)
    const settled = sgrColors(buf.slice(beforeRepaint))
    const flashed = [...sgrColors(firstFrame)].filter(code => !settled.has(code))
    assert.deepEqual(flashed, [], `first frame painted colors the settled theme never uses: ${flashed.join(', ')}`)

    // The boot screen must never contain a crash / module-resolution dump.
    const bootPlain = plain(buf)
    assert.ok(!/Error \[|ERR_MODULE_NOT_FOUND|Traceback|Cannot find module/.test(bootPlain), 'boot screen shows an error dump')

    // 2. Colors: the TUI paints SGR color codes, not a mono fallback.
    assert.ok(hasSgrColor(buf), 'no ANSI color codes in TUI output')

    // The status-line frame ("… · N session …") is the stable chrome we track.
    const framePresent = (s: string) => plain(s).includes('session') && plain(s).includes('mock model')
    assert.ok(framePresent(buf), 'status-line frame missing at boot')

    // 3. Typing lands in the composer.
    term.write('hello from the e2e harness')
    await waitFor(() => buf, s => plain(s).includes('hello from the e2e harness'), 10_000, 'typed text in composer')

    // 4. Submit → a turn runs and the reply renders. (Enter is CR in a PTY; a
    //    trailing LF covers input layers that debounce the CR.)
    const beforeSubmit = buf.length
    term.write('\r')
    await sleep(600)
    term.write('\n')

    await waitFor(() => buf, s => s.includes(MOCK_REPLY.slice(0, 24)), 30_000, 'assistant reply rendered')
    assert.ok(buf.length > beforeSubmit, 'screen did not advance after submit')

    // 5. UI stability: the chrome is intact after the run — status frame still
    //    present, still colored, and no error leaked onto the screen during it.
    const afterPlain = plain(buf)
    assert.ok(framePresent(buf), 'status-line frame vanished after the run')
    assert.ok(hasSgrColor(buf), 'colors dropped after the run')
    assert.ok(!/Error \[|Traceback|Cannot find module|undefined is not/.test(afterPlain), 'an error leaked onto the screen during the run')

    // The completed-turn marker (✓) proves the model actually ran a turn.
    assert.ok(/✓/.test(buf), 'turn-complete marker (✓) never appeared')

    // 6. Multi-agent while one is busy. E2E_PET_STALL keeps agent A's turn
    //    running; Ctrl+X opens the switcher and TYPING starts agent B.
    term.write('E2E_PET_STALL task alpha')
    await sleep(400)
    term.write('\r')
    await waitFor(() => buf, s => s.includes('E2E_PET_STALL task alpha'), 10_000, 'agent A prompt submitted')
    await sleep(2500)

    let mark = buf.length
    term.write('\x18')
    await waitFor(() => buf.slice(mark), s => plain(s).includes('Sessions'), 10_000, 'switcher opens while busy')
    await sleep(800)
    assert.ok(plain(buf.slice(mark)).includes('0 resumable'), 'the busy agent is also offered as a resumable session')

    term.write('task bravo')
    await sleep(500)
    term.write('\r')
    await waitFor(() => buf, s => plain(s).includes('2 sessions'), 20_000, 'typing in the switcher starts agent B')

    // Switch back to agent A (row 1; B is current on row 2): its running
    // prompt shows once — not repeated behind a "next turn" divider.
    await sleep(1500)
    mark = buf.length
    term.write('\x18')
    await waitFor(() => buf.slice(mark), s => plain(s).includes('2 live'), 10_000, 'switcher lists both agents')
    term.write('\u001b[A')
    await sleep(300)
    term.write('\r')
    mark = buf.length
    await waitFor(() => buf.slice(mark), s => plain(s).includes('task alpha'), 10_000, 'switched back to agent A')
    await sleep(1500)
    // The bug's shape: the same prompt, a "next turn" divider, the prompt again.
    assert.ok(
      !/❯ E2E_PET_STALL task alpha[\s\S]*?next turn[\s\S]*?❯ E2E_PET_STALL task alpha/.test(plain(buf.slice(mark))),
      'agent A shows its prompt twice after switching back'
    )

    console.log('TUI e2e OK — boot, no palette flash, colors, composer, run, reply, stable chrome, turn marker, multi-agent.')
  } finally {
    await cleanup()
  }
}

main().then(
  () => process.exit(0),
  err => {
    console.error('TUI e2e FAILED:', err?.message ?? err)
    process.exit(1)
  }
)
