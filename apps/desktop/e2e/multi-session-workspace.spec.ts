import { execFileSync } from 'node:child_process'
import * as fs from 'node:fs'
import * as path from 'node:path'

import type { Page } from '@playwright/test'

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
import { PET_STALL_TRIGGER, startMockServer, type MockServer } from './mock-server'
import { RealSessionBuilder } from './real-session-builder'

// Two chats in two repos, one of them busy in the background. The composer's
// git row and a new chat's folder must always belong to the chat on screen.

const HOLD_PROMPT = 'E2E_MULTI_SESSION_HOLD'
const ALPHA_SEED = 'Alpha seed chat'
const BETA_SEED = 'Beta seed chat'
const SURFACE = '[data-composer-target]:not([data-pane-hidden] [data-composer-target])'

function createRepo(root: string, name: string, branch: string, dirtyLines: number): string {
  const repo = path.join(root, name)

  fs.mkdirSync(repo, { recursive: true })
  const git = (...args: string[]) => execFileSync('git', args, { cwd: repo })
  git('init', `--initial-branch=${branch}`)
  git('config', 'user.email', 'e2e@example.com')
  git('config', 'user.name', 'JettsTUI E2E')
  fs.writeFileSync(path.join(repo, 'notes.txt'), 'seed\n', 'utf8')
  git('add', 'notes.txt')
  git('commit', '-m', 'initial')

  if (dirtyLines > 0) {
    fs.writeFileSync(path.join(repo, 'notes.txt'), Array.from({ length: dirtyLines }, (_, i) => `line ${i}`).join('\n'))
  }

  return repo
}

function codingRow(page: Page) {
  return page.locator(SURFACE).last().locator('.coding-status-bar')
}

function sessionRow(page: Page, title: string) {
  return page
    .locator('[data-slot="sidebar"] button')
    .filter({ hasText: new RegExp('^\\s*' + title + '\\s*$') })
    .first()
}

async function openStoredChat(page: Page, title: string, transcript: string): Promise<void> {
  await sessionRow(page, title).click()
  await waitForVisibleTranscript(page, transcript)
}

async function waitForVisibleTranscript(page: Page, text: string): Promise<void> {
  await page.waitForFunction(
    expected =>
      Array.from(document.querySelectorAll('[data-slot="aui_thread-viewport"]')).some(
        viewport => !viewport.closest('[data-pane-hidden]') && (viewport.textContent ?? '').includes(expected),
      ),
    text,
    { timeout: 20_000 },
  )
}

async function send(page: Page, text: string): Promise<void> {
  const composer = page.locator(SURFACE).last().locator('[contenteditable="true"]').first()

  await composer.click()
  await composer.type(text, { delay: 2 })
  await page.keyboard.press('Enter')
}

/** Every distinct text the row showed over `ms`, sampled every 50ms. */
async function sampleRow(page: Page, ms: number): Promise<string[]> {
  const seen = new Set<string>()
  const until = Date.now() + ms

  while (Date.now() < until) {
    seen.add((await codingRow(page).textContent({ timeout: 1_000 }).catch(() => '')) ?? '')
    await page.waitForTimeout(50)
  }

  return [...seen]
}

let fixture: MockBackendFixture | null = null
let mock: MockServer
let betaRepoName = ''

test.beforeAll(async () => {
  const sandbox = createSandbox('multi-session-workspace')
  const alpha = createRepo(sandbox.root, 'alpha-repo', 'alpha-branch', 400)
  const beta = createRepo(sandbox.root, 'beta-repo', 'beta-branch', 0)
  betaRepoName = path.basename(beta)
  mock = await startMockServer({ holdFirstStreamForPrompt: HOLD_PROMPT })

  writeMockProviderConfig(sandbox.jettstuiHome, mock.url)
  fs.appendFileSync(path.join(sandbox.jettstuiHome, 'config.yaml'), `\nterminal:\n  cwd: ${alpha}\n`, 'utf8')
  writeEnvFile(sandbox.jettstuiHome)

  const builder = await RealSessionBuilder.start(sandbox.jettstuiHome)

  try {
    await builder.createSession({ title: 'alpha', cwd: alpha, turns: [ALPHA_SEED] })
    await builder.createSession({ title: 'beta', cwd: beta, turns: [BETA_SEED] })
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
})

test.afterAll(async () => {
  await fixture?.cleanup()
  fixture = null
})

test('a background chat never paints its repo onto the visible chat', async () => {
  test.slow()
  const page = fixture!.page

  await openStoredChat(page, 'alpha', ALPHA_SEED)
  await expect(codingRow(page)).toContainText('alpha-branch', { timeout: 15_000 })

  await send(page, `${HOLD_PROMPT} keep working`)
  await mock.waitForHeldStream()

  await openStoredChat(page, 'beta', BETA_SEED)
  await expect(codingRow(page)).toContainText('beta-branch', { timeout: 15_000 })

  // Let the alpha turn stream and finish while beta is on screen.
  mock.releaseHeldStream()
  const seen = await sampleRow(page, 5_000)

  expect(seen.filter(text => text.includes('alpha-branch'))).toEqual([])
})

const MAIN_ROW = '[data-composer-target="main"]:not([data-pane-hidden] *) .coding-status-bar'
const TILE_ROW = '[data-composer-target^="tile:"]:not([data-pane-hidden] *) .coding-status-bar'

/** Drag a sidebar row onto the workspace's right edge to open it side by side.
 *  The pointer gesture occasionally fails to engage, so retry until a tile shows. */
async function openInSplit(page: Page, title: string): Promise<void> {
  const tiles = page.locator('[data-composer-target^="tile:"]:not([data-pane-hidden] *)')

  for (let attempt = 0; attempt < 4 && (await tiles.count()) === 0; attempt++) {
    const rowBox = (await sessionRow(page, title).boundingBox())!
    const zone = (await page.locator('[data-session-anchor="workspace"]').boundingBox())!
    const from = { x: rowBox.x + rowBox.width / 2, y: rowBox.y + rowBox.height / 2 }
    const to = { x: zone.x + zone.width - 20, y: zone.y + zone.height / 2 }

    await page.mouse.move(from.x, from.y)
    await page.mouse.down()

    for (let i = 1; i <= 15; i++) {
      await page.mouse.move(from.x + ((to.x - from.x) * i) / 15, from.y + ((to.y - from.y) * i) / 15)
      await page.waitForTimeout(40)
    }

    await page.mouse.up()
    await tiles.first().waitFor({ timeout: 3_000 }).catch(() => undefined)
  }

  await expect(tiles.first()).toBeVisible()
}

test('chats side by side each show their own repo in the git row', async () => {
  test.slow()
  const page = fixture!.page

  await openStoredChat(page, 'alpha', ALPHA_SEED)
  await expect(page.locator(MAIN_ROW)).toContainText('alpha-branch', { timeout: 15_000 })

  await openInSplit(page, 'beta')
  await expect(page.locator(TILE_ROW)).toContainText('beta-branch', { timeout: 20_000 })
  await expect(page.locator(MAIN_ROW)).toContainText('alpha-branch')

  for (let i = 0; i < 30; i++) {
    await expect(page.locator(TILE_ROW)).not.toContainText('alpha-branch')
    await expect(page.locator(MAIN_ROW)).not.toContainText('beta-branch')
    await page.waitForTimeout(100)
  }
})

test('a new chat in a project folder opens there without moving the open chat', async () => {
  test.slow()
  const page = fixture!.page

  // Close the split from the previous test so only the main chat is open.
  await page.reload()
  await openStoredChat(page, 'alpha', ALPHA_SEED)
  await expect(page.locator(MAIN_ROW)).toContainText('alpha-branch', { timeout: 15_000 })
  await send(page, `${PET_STALL_TRIGGER} stay busy`)

  const showProjects = page.getByRole('button', { name: 'Show projects' })

  if (await showProjects.isVisible().catch(() => false)) {
    await showProjects.click()
  }

  await page.getByRole('button', { name: `New session in ${betaRepoName}` }).first().click()
  await expect(page.locator(TILE_ROW)).toContainText('beta-branch', { timeout: 20_000 })

  await openStoredChat(page, 'alpha', ALPHA_SEED)
  const seen = await sampleRows(page, MAIN_ROW, 3_000)

  expect(seen.filter(text => text.includes('beta-branch'))).toEqual([])
  await expect(page.locator(MAIN_ROW)).toContainText('alpha-branch')
})

async function sampleRows(page: Page, selector: string, ms: number): Promise<string[]> {
  const seen = new Set<string>()
  const until = Date.now() + ms

  while (Date.now() < until) {
    seen.add((await page.locator(selector).first().textContent({ timeout: 1_000 }).catch(() => '')) ?? '')
    await page.waitForTimeout(50)
  }

  return [...seen]
}
