/**
 * E2E: stopping a spec agent mid-request, then retrying, from the Specs page.
 *
 * The mock stalls the first requirements draft (the model never answers), so
 * the run is genuinely waiting on the model when the user presses Stop. The
 * page must then say it stopped — not show the cancellation sentinel as the
 * agent's reply, and not keep claiming the requirements are being written —
 * and Retry must resume the draft with the user's own description.
 *
 * Prerequisite: `npm run build` must have been run so dist/ exists.
 */

import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { type MockBackendFixture, setupMockBackend, waitForAppReady } from './fixtures'
import { SPEC_E2E_NAME } from './mock-server'
import { expect, test } from './test'

let fixture: MockBackendFixture | null = null
let workspace = ''

test.beforeAll(async () => {
  workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'jettstui-e2e-spec-stop-'))
  fixture = await setupMockBackend({
    extraConfig: `terminal:\n  cwd: ${JSON.stringify(workspace)}`,
    mockServer: { stallFirstSpecRequirements: true }
  })
  await waitForAppReady(fixture!, 120_000)
})

test.afterAll(async () => {
  await fixture?.cleanup()
  fixture = null
  fs.rmSync(workspace, { recursive: true, force: true })
})

test('a stopped spec says so honestly, and Retry finishes it', async () => {
  const page = fixture!.page

  const composer = page.locator('[contenteditable="true"]').first()
  await composer.click()
  await composer.type('hello', { delay: 10 })
  await page.keyboard.press('Enter')
  await expect(page.getByText('Hello from the mock inference server').first()).toBeVisible({ timeout: 30_000 })

  await page.getByRole('button', { name: 'Specs', exact: true }).click()
  await expect(page.getByText('Plan it before you build it')).toBeVisible({ timeout: 15_000 })
  // The page works in the chat's project, shown in the picker.
  await expect(page.getByTestId('project-picker')).toContainText(path.basename(workspace))

  await page.getByLabel('New spec').fill('Offline search')
  await page.getByRole('button', { name: 'Create spec' }).click()

  // The agent is waiting on the (stalled) model: running, with Stop.
  const run = page.getByTestId('spec-run')
  await expect(run).toHaveAttribute('data-status', 'running', { timeout: 30_000 })
  await expect(page.getByRole('tab', { name: /Requirements/ })).toHaveAttribute('data-state', 'drafting')
  // Wait until the agent is really blocked on the model, then Stop — the
  // situation in the report ("interrupted: waiting for model response").
  await expect.poll(() => fixture!.mock.stalledSpecRequests(), { timeout: 30_000 }).toBe(1)
  await run.getByRole('button', { name: /Stop/ }).click()

  // Stopped: said plainly, no sentinel as a reply, no "being written".
  await expect(run).toHaveAttribute('data-status', 'interrupted', { timeout: 30_000 })
  await expect(run).toContainText('Stopped before it finished')
  await expect(page.getByText(/Operation interrupted/)).toHaveCount(0)
  await expect(page.getByText(/being written/i)).toHaveCount(0)
  await expect(page.getByRole('tab', { name: /Requirements/ })).toHaveAttribute('data-state', 'upcoming')
  await expect(page.getByTestId('spec-next-step')).toContainText("The requirements haven't been written yet.")

  // Retry resumes the draft (the mock answers this time).
  await run.getByRole('button', { name: /Retry/ }).click()
  const requirements = path.join(workspace, '.kiro', 'specs', SPEC_E2E_NAME, 'requirements.md')
  await expect.poll(() => fs.existsSync(requirements), { timeout: 60_000 }).toBe(true)
  await expect(page.getByTestId('spec-doc-requirements')).toContainText('THE Search SHALL', { timeout: 15_000 })
  await expect(page.getByTestId('spec-run')).toHaveAttribute('data-status', 'completed', { timeout: 15_000 })
})
