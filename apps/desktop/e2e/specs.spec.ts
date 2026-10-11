/**
 * E2E: the Specs page drives the spec workflow end to end.
 *
 * The backend runs in a sandbox workspace (terminal.cwd). From the Specs page
 * the test creates a spec, approves requirements and design, and starts the
 * first task. Each action runs headlessly through `spec.run` — no chat is
 * opened — the real backend turns it into the phase prompt, the mock model writes the phase's document with a
 * real write_file call, and the page picks the file up from disk.
 *
 * Prerequisite: `npm run build` must have been run so dist/ exists.
 */

import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import type { Page } from '@playwright/test'

import { type MockBackendFixture, setupMockBackend, waitForAppReady } from './fixtures'
import { SPEC_E2E_NAME } from './mock-server'
import { expect, test } from './test'

let fixture: MockBackendFixture | null = null
let workspace = ''

test.beforeAll(async () => {
  workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'jettstui-e2e-specs-'))
  fixture = await setupMockBackend({ extraConfig: `terminal:\n  cwd: ${JSON.stringify(workspace)}` })
  await waitForAppReady(fixture!, 120_000)
})

test.afterAll(async () => {
  await fixture?.cleanup()
  fixture = null
  fs.rmSync(workspace, { recursive: true, force: true })
})

const specFile = (name: string) => path.join(workspace, '.kiro', 'specs', SPEC_E2E_NAME, name)

async function openSpecs(page: Page) {
  await page.getByRole('button', { name: 'Specs', exact: true }).click()
  await expect(page.getByTestId('specs-view')).toBeVisible({ timeout: 15_000 })
}

test('specs page runs the spec workflow: requirements → design → tasks → task', async () => {
  const page = fixture!.page

  // A first chat establishes the workspace the Specs page reads.
  const composer = page.locator('[contenteditable="true"]').first()
  await composer.click()
  await composer.type('hello', { delay: 10 })
  await page.keyboard.press('Enter')
  await expect(page.getByText('Hello from the mock inference server').first()).toBeVisible({ timeout: 30_000 })

  await openSpecs(page)
  // A project with no specs opens on the welcome composer.
  await expect(page.getByText('Plan it before you build it')).toBeVisible({ timeout: 15_000 })

  // Every action runs headlessly on this page: it never navigates to a chat,
  // and spec work never shows up in the session list.
  const view = page.getByTestId('specs-view')
  const stillHere = async () => {
    await expect(view).toBeVisible()
    await expect(page.getByText(/REQUIREMENTS phase|DESIGN phase|TASKS phase|Execute task|\/spec /)).toHaveCount(0)
  }

  // Create (guided) → the agent writes the requirements; the reply shows here.
  await page.getByLabel('New spec').fill('Offline search')
  await page.getByRole('button', { name: 'Create spec' }).click()
  await expect.poll(() => fs.existsSync(specFile('requirements.md')), { timeout: 60_000 }).toBe(true)
  expect(fs.existsSync(specFile('.config.kiro'))).toBe(true)
  expect(fs.existsSync(specFile('design.md'))).toBe(false)
  await expect(page.getByTestId('spec-doc-requirements')).toContainText('THE Search SHALL', { timeout: 15_000 })
  await expect(page.getByTestId('spec-run')).toHaveAttribute('data-status', 'completed', { timeout: 15_000 })
  await expect(page.getByTestId('spec-run-reply')).toContainText('Wrote requirements.md')
  await stillHere()

  // Approve requirements → design.
  await page.getByTestId('spec-next-step').getByRole('button', { name: 'Approve → design' }).click()
  await expect.poll(() => fs.existsSync(specFile('design.md')), { timeout: 60_000 }).toBe(true)
  await expect(page.getByTestId('spec-doc-design')).toContainText('local inverted index', { timeout: 15_000 })
  await stillHere()

  // Approve design → task list.
  await expect(page.getByTestId('spec-next-step')).toBeVisible({ timeout: 15_000 })
  await page.getByTestId('spec-next-step').getByRole('button', { name: 'Approve → task list' }).click()
  await expect.poll(() => fs.existsSync(specFile('tasks.md')), { timeout: 60_000 }).toBe(true)
  await expect(page.getByTestId('spec-task')).toHaveCount(2, { timeout: 15_000 })
  await stillHere()

  // Start the first task → the agent checks it off.
  await expect(page.getByTestId('spec-next-step')).toBeVisible({ timeout: 15_000 })
  await page.getByTestId('spec-next-step').getByRole('button', { name: /Start task 1/ }).click()
  await expect
    .poll(() => fs.readFileSync(specFile('tasks.md'), 'utf8'), { timeout: 60_000 })
    .toContain('- [x] 1. Build the local index')
  await expect(page.locator('[data-testid="spec-task"][data-task="1"]')).toHaveAttribute('data-status', 'completed', {
    timeout: 15_000
  })
  await expect(page.getByTestId('spec-phase').first()).toHaveText('In progress')
  await stillHere()
})
