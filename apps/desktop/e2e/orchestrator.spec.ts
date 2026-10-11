/**
 * E2E: the Orchestrator page drives a real multi-stage flow.
 *
 * Opens the page from the sidebar, enables the orchestrator (persisted to
 * config.yaml through the orchestrator.save RPC), runs a task, and checks that
 * the backend ran every stage as a subagent and the chat shows the outcome.
 *
 * Prerequisite: `npm run build` must have been run so dist/ exists.
 */

import fs from 'node:fs'
import path from 'node:path'

import { type MockBackendFixture, setupMockBackend, waitForAppReady } from './fixtures'
import { ORCHESTRATOR_DONE, ORCHESTRATOR_STAGE_MARKERS, receivedUserTexts } from './mock-server'
import { expect, test } from './test'

let fixture: MockBackendFixture | null = null

test.beforeAll(async () => {
  fixture = await setupMockBackend()
  await waitForAppReady(fixture!, 120_000)
})

test.afterAll(async () => {
  await fixture?.cleanup()
  fixture = null
})

test('orchestrator page configures roles and runs a flow', async () => {
  const page = fixture!.page

  await page.getByText('Orchestrator', { exact: true }).first().click()
  await expect(page.getByRole('heading', { name: 'Orchestrator' })).toBeVisible({ timeout: 15_000 })

  for (const role of ['Planner', 'Executor', 'Reviewer', 'Security & quality']) {
    await expect(page.getByText(role, { exact: true })).toBeVisible()
  }

  // Auto resolves every role to the only configured model.
  await expect(page.getByText('Auto → mock-model')).toHaveCount(4)

  const toggle = page.getByRole('switch')
  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-checked', 'true')

  const configPath = path.join(fixture!.sandbox.jettstuiHome, 'config.yaml')
  await expect.poll(() => fs.readFileSync(configPath, 'utf8')).toMatch(/orchestrator:\s*\n\s*enabled: true/)

  await page.getByLabel('Run a task').fill('Add a dark mode toggle')
  await page.getByRole('button', { name: 'Run in new chat' }).click()

  await page.waitForFunction(text => (document.body.textContent ?? '').includes(text), ORCHESTRATOR_DONE, {
    timeout: 60_000
  })

  const prompts = receivedUserTexts()

  for (const marker of ORCHESTRATOR_STAGE_MARKERS) {
    expect(prompts.some(text => text.startsWith(marker))).toBe(true)
  }

})
