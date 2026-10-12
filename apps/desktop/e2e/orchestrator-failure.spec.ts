/**
 * E2E: an Orchestrator run whose model calls fail ends as failed.
 *
 * Reported bug class: a stage subagent that gave up ("API call failed after 3
 * retries: HTTP 404 …") was counted as a completed stage, its error notice
 * passed along as the stage's work. The mock answers 404 for anything that
 * mentions the trigger, so every stage of this task fails.
 *
 * Prerequisite: `npm run build` must have been run so dist/ exists.
 */

import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { type MockBackendFixture, setupMockBackend, waitForAppReady } from './fixtures'
import { PROVIDER_404_TRIGGER } from './mock-server'
import { expect, test } from './test'

let fixture: MockBackendFixture | null = null
let workspace = ''

test.beforeAll(async () => {
  workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'jettstui-e2e-orchestrator-failure-'))
  fixture = await setupMockBackend({ extraConfig: `terminal:\n  cwd: ${JSON.stringify(workspace)}` })
  await waitForAppReady(fixture!, 120_000)
})

test.afterAll(async () => {
  await fixture?.cleanup()
  fixture = null
  fs.rmSync(workspace, { recursive: true, force: true })
})

test('a run whose stages cannot reach the model is reported as failed', async () => {
  const page = fixture!.page

  const composer = page.locator('[contenteditable="true"]').first()
  await composer.click()
  await composer.type('hello', { delay: 5 })
  await page.keyboard.press('Enter')
  await expect(page.getByText('Hello from the mock inference server').first()).toBeVisible({ timeout: 30_000 })

  await page.getByRole('button', { name: 'Orchestrator', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Orchestrator' })).toBeVisible({ timeout: 15_000 })

  await page.getByLabel('Run a task').fill(`Add a dark mode toggle ${PROVIDER_404_TRIGGER}`)
  await page.getByRole('button', { name: 'Run', exact: true }).click()

  const run = page.getByTestId('orchestrator-run')
  await expect(run).toHaveAttribute('data-status', 'failed', { timeout: 120_000 })
  await expect(run.locator('[data-testid="flow-agent"][data-status="completed"]')).toHaveCount(0)
})
