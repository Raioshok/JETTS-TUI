import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { type Locator } from '@playwright/test'

import {
  buildAppEnv,
  createSandbox,
  launchDesktop,
  type MockBackendFixture,
  waitForAppReady,
  writeEnvFile,
  writeMockProviderConfig
} from './fixtures'
import { startMockServer } from './mock-server'
import { RealSessionBuilder } from './real-session-builder'
import { expect, test } from './test'

// The default Ivory look + Code mode, driven end to end against a real
// backend: the header "Code" switch rearranges the layout (file tree | editor
// | chat), files open as tabs with a breadcrumb + status bar, Copy reaches the
// clipboard, and "Chat" restores the layout without leaving the session.

const CLIENT = 'export class ApiClient {\n  constructor(private readonly baseUrl: string) {}\n}\n'
const TYPES = 'export interface ClientConfig {\n  baseUrl?: string\n}\n'
const SESSION_PROMPT = 'Review the API client for retry bugs'

let fixture: MockBackendFixture | null = null
let projectRoot = ''

function writeProject(): string {
  projectRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'jt-code-mode-'))
  const dir = path.join(projectRoot, 'demo-api-client')
  fs.mkdirSync(path.join(dir, 'src'), { recursive: true })
  fs.writeFileSync(path.join(dir, 'src', 'client.ts'), CLIENT)
  fs.writeFileSync(path.join(dir, 'src', 'types.ts'), TYPES)
  fs.writeFileSync(path.join(dir, 'README.md'), '# demo-api-client\n')

  return dir
}

const left = async (locator: Locator) => (await locator.boundingBox())!.x

test.beforeAll(async () => {
  const project = writeProject()
  const sandbox = createSandbox('code-mode')
  const mock = await startMockServer()
  writeMockProviderConfig(sandbox.jettstuiHome, mock.url)
  writeEnvFile(sandbox.jettstuiHome)

  const builder = await RealSessionBuilder.start(sandbox.jettstuiHome)

  try {
    await builder.createSession({ title: 'API client', cwd: project, turns: [SESSION_PROMPT] })
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
      fs.rmSync(projectRoot, { force: true, recursive: true })
    }
  }
  await waitForAppReady(fixture, 120_000)
})

test.afterAll(async () => {
  await fixture?.cleanup()
  fixture = null
})

test('Ivory is the default look', async () => {
  const root = fixture!.page.locator('html')

  await expect(root).toHaveAttribute('data-jettstui-theme', 'ivory')
  await expect(root).toHaveAttribute('data-jettstui-mode', 'light')
})

test('Code mode: file tree, tabs, breadcrumb, status bar, copy, and back to Chat', async () => {
  test.slow()
  const page = fixture!.page
  const app = fixture!.app

  await page
    .locator('[data-slot="sidebar"] button')
    .filter({ hasText: /API client/ })
    .first()
    .click()
  await expect(page.getByText(SESSION_PROMPT).first()).toBeVisible({ timeout: 30_000 })

  const modes = page.locator('[data-slot="nav-mode"]')
  await modes.getByRole('button', { name: 'Code', exact: true }).click()
  await expect(modes.getByRole('button', { name: 'Code', exact: true })).toHaveAttribute('aria-current', 'page')
  // Switching layout must not leave the open session.
  await expect(page.getByText(SESSION_PROMPT).first()).toBeVisible()

  const tree = page.locator('[data-slot="file-tree-pane"]')
  await expect(tree).toBeVisible({ timeout: 20_000 })
  await tree
    .locator('[aria-expanded]')
    .filter({ hasText: /^\s*src\s*$/ })
    .first()
    .click()

  await tree
    .locator('[aria-selected]')
    .filter({ hasText: /client\.ts/ })
    .first()
    .dblclick()
  const rail = page.locator('[data-slot="preview-rail"]')
  await expect(rail.getByText('export class ApiClient')).toBeVisible({ timeout: 20_000 })

  const leaf = rail.locator('[data-slot="file-breadcrumb-leaf"]')
  await expect(leaf).toHaveText('client.ts')
  const status = rail.locator('[data-slot="source-status"]')
  await expect(status).toContainText('TypeScript')
  await expect(status).toContainText('3 lines')

  // Layout: file tree | editor | chat.
  const composer = page.locator('[data-slot="composer-root"]').first()
  expect(await left(tree)).toBeLessThan(await left(rail))
  expect(await left(rail)).toBeLessThan(await left(composer))

  // A second file opens a second tab; tabs switch the editor + breadcrumb.
  await tree
    .locator('[aria-selected]')
    .filter({ hasText: /types\.ts/ })
    .first()
    .dblclick()
  await expect(leaf).toHaveText('types.ts')
  const tabs = rail.getByRole('tab')
  await expect(tabs).toHaveCount(2)
  await tabs.filter({ hasText: 'client.ts' }).click()
  await expect(leaf).toHaveText('client.ts')
  await expect(tabs.filter({ hasText: 'client.ts' })).toHaveAttribute('aria-selected', 'true')

  // Copy puts the whole file on the clipboard.
  await rail.getByRole('button', { name: 'Copy' }).click()
  await expect.poll(() => app.evaluate(({ clipboard }) => clipboard.readText())).toBe(CLIENT)

  // Closing a tab removes it.
  await rail.locator('[data-pane-tab]').filter({ hasText: 'types.ts' }).hover()
  await rail
    .locator('[data-pane-tab]')
    .filter({ hasText: 'types.ts' })
    .getByRole('button', { name: 'Close tab' })
    .click()
  await expect(tabs).toHaveCount(1)

  // Back to Chat: code mode off, the tree returns to its usual right-hand
  // spot, and the session is still the one on screen.
  await modes.getByRole('button', { name: 'Chat', exact: true }).click()
  await expect(modes.getByRole('button', { name: 'Chat', exact: true })).toHaveAttribute('aria-current', 'page')
  await expect(page.getByText(SESSION_PROMPT).first()).toBeVisible()
  await expect(tree).toBeVisible()
  expect(await left(tree)).toBeGreaterThan(await left(composer))
})
