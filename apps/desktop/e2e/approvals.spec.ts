/**
 * E2E: a command the approval guard flags waits for the user, and both
 * answers reach the agent — allow runs it, deny blocks it and the agent is told.
 *
 * Manual approvals so the decision is the user's (smart mode would ask the
 * mock model to judge).
 *
 * Prerequisite: `npm run build` must have been run so dist/ exists.
 */

import { type MockBackendFixture, setupMockBackend, waitForAppReady } from './fixtures'
import { APPROVAL_COMMAND, APPROVAL_DONE, APPROVAL_TRIGGER } from './mock-server'
import { expect, test } from './test'

let fixture: MockBackendFixture | null = null

test.beforeAll(async () => {
  fixture = await setupMockBackend({ extraConfig: 'approvals:\n  mode: manual' })
  await waitForAppReady(fixture, 120_000)
})

test.afterAll(async () => {
  await fixture?.cleanup()
  fixture = null
})

async function ask(text: string) {
  const page = fixture!.page
  await page.keyboard.press('Control+n')
  const composer = page.locator('[contenteditable="true"]:visible').last()
  await composer.click()
  await composer.type(text, { delay: 5 })
  await page.keyboard.press('Enter')
}

test('allowing a flagged command runs it and the turn finishes', async () => {
  const page = fixture!.page
  await ask(`${APPROVAL_TRIGGER} allow`)

  const card = page.getByText(APPROVAL_COMMAND).last()
  await expect(card).toBeVisible({ timeout: 30_000 })
  // The turn is waiting on the user, not finished.
  await expect(page.getByText(APPROVAL_DONE)).toHaveCount(0)
  await page.screenshot({ path: test.info().outputPath('approval-card.png') })

  await page.getByRole('button', { name: /^Run / }).click()
  await expect(page.getByText(APPROVAL_DONE).last()).toBeVisible({ timeout: 30_000 })
})

test('denying a flagged command blocks it and tells the agent', async () => {
  const page = fixture!.page
  await ask(`${APPROVAL_TRIGGER} deny`)

  await expect(page.getByText(APPROVAL_COMMAND).last()).toBeVisible({ timeout: 30_000 })
  await page.getByRole('button', { name: /^Reject / }).click()

  await expect(page.getByText(APPROVAL_DONE).last()).toBeVisible({ timeout: 30_000 })
})
