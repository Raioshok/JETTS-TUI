import { execFileSync } from 'node:child_process'
import * as fs from 'node:fs'
import * as path from 'node:path'

import { test, expect } from './test'

import {
  buildAppEnv,
  createSandbox,
  launchDesktop,
  writeEnvFile,
  writeMockProviderConfig,
  type MockBackendFixture,
  waitForAppReady,
} from './fixtures'
import { startMockServer } from './mock-server'
import { RealSessionBuilder } from './real-session-builder'

// Right after launch, with no chat open: "New session in <project>" must start
// the chat in that project, not the configured home folder. (A project whose
// folder is gone is rejected by session.create — see
// tests/tui_gateway/test_session_create_missing_cwd.py.)

const MAIN_ROW = '[data-composer-target="main"]:not([data-pane-hidden] *) .coding-status-bar'
function createRepo(root: string, name: string, branch: string): string {
  const repo = path.join(root, name)

  fs.mkdirSync(repo, { recursive: true })
  const git = (...args: string[]) => execFileSync('git', args, { cwd: repo })
  git('init', `--initial-branch=${branch}`)
  git('config', 'user.email', 'e2e@example.com')
  git('config', 'user.name', 'JettsTUI E2E')
  fs.writeFileSync(path.join(repo, 'notes.txt'), 'seed\n', 'utf8')
  git('add', 'notes.txt')
  git('commit', '-m', 'initial')

  return repo
}

let fixture: MockBackendFixture | null = null

test.beforeAll(async () => {
  const sandbox = createSandbox('new-session-in-project')
  const home = createRepo(sandbox.root, 'home-repo', 'home-branch')
  const target = createRepo(sandbox.root, 'target-repo', 'target-branch')
  const mock = await startMockServer()

  writeMockProviderConfig(sandbox.jettstuiHome, mock.url)
  fs.appendFileSync(path.join(sandbox.jettstuiHome, 'config.yaml'), `\nterminal:\n  cwd: ${home}\n`, 'utf8')
  writeEnvFile(sandbox.jettstuiHome)

  const builder = await RealSessionBuilder.start(sandbox.jettstuiHome)

  try {
    await builder.createSession({ title: 'target', cwd: target, turns: ['Target seed chat'] })
  } finally {
    await builder.close()
  }

  const { app, page } = await launchDesktop(buildAppEnv(sandbox))
  fixture = {
    app,
    page,
    mock,
    mockUrl: mock.url,
    sandbox,
    cleanup: async () => {
      await app.close().catch(() => undefined)
      await mock.close()
      sandbox.cleanup()
    },
  }

  await waitForAppReady(fixture, 120_000)

  const showProjects = page.getByRole('button', { name: 'Show projects' })

  if (await showProjects.isVisible().catch(() => false)) {
    await showProjects.click()
  }
})

test.afterAll(async () => {
  await fixture?.cleanup()
  fixture = null
})

async function send(text: string): Promise<void> {
  const composer = fixture!.page.locator('[data-composer-target="main"] [contenteditable="true"]').first()

  await composer.click()
  await composer.type(text, { delay: 2 })
  await fixture!.page.keyboard.press('Enter')
}

test('starts the chat in the clicked project', async () => {
  const page = fixture!.page

  await page.getByRole('button', { name: 'New session in target-repo' }).first().click()
  await expect(page.locator(MAIN_ROW)).toContainText('target-branch', { timeout: 20_000 })

  await send('first message in target')
  await page.waitForFunction(
    text => (document.querySelector('[data-slot="aui_thread-viewport"]')?.textContent ?? '').includes(text),
    'first message in target',
    { timeout: 20_000 },
  )
  await expect(page.locator(MAIN_ROW)).toContainText('target-branch')
  await expect(page.locator(MAIN_ROW)).not.toContainText('home-branch')
})
