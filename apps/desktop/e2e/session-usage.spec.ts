import { test, expect } from './test'

import { buildAppEnv, createSandbox, launchDesktop, writeEnvFile, writeMockProviderConfig, type MockBackendFixture, waitForAppReady } from './fixtures'
import { startMockServer } from './mock-server'
import { RealSessionBuilder } from './real-session-builder'

// Right-clicking a stored session shows "Usage" and the dialog reports the
// session's working time and token counts from the real backend.

const SEED = 'Usage probe chat'

let fixture: MockBackendFixture | null = null

test.beforeAll(async () => {
  const sandbox = createSandbox('session-usage')
  const mock = await startMockServer()
  writeMockProviderConfig(sandbox.jettstuiHome, mock.url)
  writeEnvFile(sandbox.jettstuiHome)

  const builder = await RealSessionBuilder.start(sandbox.jettstuiHome)

  try {
    await builder.createSession({ title: 'usage', turns: [SEED, 'and one more turn'] })
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
    }
  }
  await waitForAppReady(fixture, 120_000)
})

test.afterAll(async () => {
  await fixture?.cleanup()
  fixture = null
})

test('right-click → Usage shows working time and token counts', async () => {
  test.slow()
  const page = fixture!.page

  // Prefer the flat session list (the project-tree view can sit on a skeleton
  // when no project exists).
  const showSessions = page.getByRole('button', { name: 'Show sessions' })

  if (await showSessions.isVisible().catch(() => false)) {
    await showSessions.click()
  }

  const row = page.locator('[data-slot="sidebar"] button').filter({ hasText: /^\s*usage\s*$/ }).first()
  await expect(row).toBeVisible({ timeout: 60_000 })
  await row.click({ button: 'right' })

  const usageItem = page.getByRole('menuitem', { name: 'Usage' })
  await expect(usageItem).toBeVisible({ timeout: 10_000 })
  await usageItem.click()

  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText('Session usage')
  await expect(dialog).toContainText('Working time')
  // The real agent ran two turns, so API calls must be a positive number.
  await expect(dialog.getByText('API calls')).toBeVisible()
  const apiRow = dialog.locator('div', { hasText: /^API calls/ }).last()
  await expect(apiRow).not.toContainText('API calls0')
})
