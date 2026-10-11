/**
 * E2E: the Orchestrator tab drives real multi-stage flows.
 *
 * 1. From the tab's Runs view, a task runs headlessly: the real backend runs
 *    every role in both phases as subagents on a hidden coordinator, the tab
 *    shows the team live and its outcome, and no chat is created.
 * 2. With the in-chat tool enabled (Team & models), a chat can still call
 *    `orchestrate`, and that flow streams into the Flow sidebar.
 *
 * Prerequisite: `npm run build` must have been run so dist/ exists.
 */

import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import type { Page } from '@playwright/test'

import { type MockBackendFixture, setupMockBackend, waitForAppReady } from './fixtures'
import { ORCHESTRATOR_DONE, ORCHESTRATOR_STAGE_MARKERS, ORCHESTRATOR_TRIGGER, receivedUserTexts } from './mock-server'
import { expect, test } from './test'

let fixture: MockBackendFixture | null = null
let workspace = ''

test.beforeAll(async () => {
  workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'jettstui-e2e-orchestrator-'))
  fixture = await setupMockBackend({ extraConfig: `terminal:\n  cwd: ${JSON.stringify(workspace)}` })
  await waitForAppReady(fixture!, 120_000)
})

test.afterAll(async () => {
  await fixture?.cleanup()
  fixture = null
  fs.rmSync(workspace, { recursive: true, force: true })
})

async function sendChat(page: Page, text: string) {
  const composer = page.locator('[contenteditable="true"]').first()
  await composer.click()
  await composer.type(text, { delay: 5 })
  await page.keyboard.press('Enter')
}

async function openOrchestrator(page: Page) {
  await page.getByRole('button', { name: 'Orchestrator', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Orchestrator' })).toBeVisible({ timeout: 15_000 })
}

test('the Orchestrator tab runs the team headlessly, without a chat', async () => {
  const page = fixture!.page

  // A first chat establishes the workspace the tab runs in.
  await sendChat(page, 'hello')
  await expect(page.getByText('Hello from the mock inference server').first()).toBeVisible({ timeout: 30_000 })

  await openOrchestrator(page)

  // Team & models: Auto resolves every role to the only configured model.
  await page.getByRole('button', { name: 'Team & models' }).click()
  for (const role of ['Planner', 'Executor', 'Reviewer', 'Security & quality']) {
    await expect(page.getByText(role, { exact: true })).toBeVisible()
  }
  await expect(page.getByText('Auto → mock-model')).toHaveCount(4)

  const configPath = path.join(fixture!.sandbox.jettstuiHome, 'config.yaml')
  await page.getByRole('button', { name: 'Economy' }).click()
  await expect.poll(() => fs.readFileSync(configPath, 'utf8')).toMatch(/auto_balance: economy/)

  // Runs: the in-chat tool is still off — runs from the tab don't need it.
  await page.getByRole('button', { name: 'Runs', exact: true }).click()

  // The project picker defaults to the chat's project and offers any folder.
  const picker = page.getByTestId('orchestrator-project')
  await expect(picker).toContainText(path.basename(workspace))
  await picker.click()
  await expect(page.getByRole('option', { name: 'Browse for a folder…' })).toBeVisible()
  await page.keyboard.press('Escape')

  await page.getByLabel('Run a task').fill('Add a dark mode toggle')
  await page.getByRole('button', { name: 'Run', exact: true }).click()

  const run = page.getByTestId('orchestrator-run')
  await expect(run).toHaveAttribute('data-status', 'approved', { timeout: 60_000 })
  await expect(run.getByTestId('flow-agent')).toHaveCount(4)
  await expect(run.locator('[data-testid="flow-agent"][data-status="completed"]')).toHaveCount(4)

  const prompts = receivedUserTexts()
  for (const marker of ORCHESTRATOR_STAGE_MARKERS) {
    expect(prompts.some(text => text.startsWith(marker))).toBe(true)
  }

  // Clicking an agent shows its work: its report and its board file.
  await run.getByRole('button', { name: "Show Executor's work" }).click()
  const detail = run.getByTestId('flow-agent-detail')
  await expect(detail.getByTestId('flow-agent-report').first()).toContainText('Made the change and verified it.')
  await expect(detail.getByTestId('flow-agent-board')).toContainText('Executor')
  await detail.getByRole('button', { name: 'Back to agents' }).click()

  // Still on the tab, and no chat was created for the flow.
  await expect(page.getByTestId('orchestrator-view')).toBeVisible()
  await expect(page.getByText(/\[(Planner|Executor|Reviewer) · /)).toHaveCount(0)
  await expect(page.getByTestId('orchestrator-run-item')).toHaveCount(1)
})

test('a chat can still orchestrate when enabled, into the Flow sidebar', async () => {
  const page = fixture!.page

  await openOrchestrator(page)
  await page.getByRole('button', { name: 'Team & models' }).click()
  const toggle = page.getByRole('switch')
  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-checked', 'true')

  const configPath = path.join(fixture!.sandbox.jettstuiHome, 'config.yaml')
  await expect.poll(() => fs.readFileSync(configPath, 'utf8')).toMatch(/orchestrator:\s*\n\s*enabled: true/)

  await page.getByRole('button', { name: 'New session' }).first().click()
  await sendChat(page, `Run this task through the ${ORCHESTRATOR_TRIGGER}: add a flag`)
  await page.waitForFunction(text => (document.body.textContent ?? '').includes(text), ORCHESTRATOR_DONE, {
    timeout: 60_000
  })

  await page.getByRole('button', { name: 'Show flow' }).click()
  const flow = page.getByTestId('flow-panel')
  await expect(flow).toBeVisible()
  await expect(flow.getByTestId('flow-run-status')).toHaveText('Approved', { timeout: 15_000 })
  await expect(flow.locator('[data-testid="flow-agent"][data-status="completed"]')).toHaveCount(4)
})
