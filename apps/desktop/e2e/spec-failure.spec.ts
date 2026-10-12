/**
 * E2E: a spec run whose model calls fail is reported as failed — not "Done".
 *
 * Reported bug: a provider answering HTTP 404 (a misrouted endpoint) made the
 * agent give up with "API call failed after 3 retries: HTTP 404 …", and the
 * Specs page showed that notice under a green "Done" check as if it were the
 * agent's reply. The mock answers 404 for anything mentioning the trigger.
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
  workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'jettstui-e2e-spec-failure-'))
  fixture = await setupMockBackend({ extraConfig: `terminal:\n  cwd: ${JSON.stringify(workspace)}` })
  await waitForAppReady(fixture!, 120_000)
})

test.afterAll(async () => {
  await fixture?.cleanup()
  fixture = null
  fs.rmSync(workspace, { recursive: true, force: true })
})

test('a spec run that cannot reach the model shows Failed with the error', async () => {
  const page = fixture!.page

  const composer = page.locator('[contenteditable="true"]').first()
  await composer.click()
  await composer.type('hello', { delay: 10 })
  await page.keyboard.press('Enter')
  await expect(page.getByText('Hello from the mock inference server').first()).toBeVisible({ timeout: 30_000 })

  await page.getByRole('button', { name: 'Specs', exact: true }).click()
  await expect(page.getByText('Plan it before you build it')).toBeVisible({ timeout: 15_000 })

  await page.getByLabel('New spec').fill(`Offline search ${PROVIDER_404_TRIGGER}`)
  await page.getByRole('button', { name: 'Create spec' }).click()

  const run = page.getByTestId('spec-run')
  await expect(run).toHaveAttribute('data-status', 'running', { timeout: 30_000 })
  // The agent retries before giving up; then the run must read as failed.
  await expect(run).toHaveAttribute('data-status', 'failed', { timeout: 90_000 })
  await expect(page.getByTestId('spec-run-error')).toContainText('404')
  await expect(page.getByTestId('spec-run-reply')).toHaveCount(0)
  await expect(run.getByRole('button', { name: /Retry/ })).toBeVisible()
})
