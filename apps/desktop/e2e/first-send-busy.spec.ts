/**
 * E2E: the first message of a new chat stays stoppable the whole time.
 *
 * Reported bug: right after the first send the route re-homes onto the
 * just-created session while the backend is still building its agent. For
 * about a second the chat looked idle — no Stop button, no thinking indicator,
 * no "running" dot — because (a) the optimistic busy write detached the new
 * session from its stored id, and (b) the liveness poll read the backend's
 * "starting" status as idle and overwrote the in-flight turn.
 *
 * The mock never answers this prompt, so the turn stays in flight.
 *
 * Prerequisite: `npm run build` must have been run so dist/ exists.
 */

import { type MockBackendFixture, setupMockBackend, waitForAppReady } from './fixtures'
import { PET_STALL_TRIGGER } from './mock-server'
import { expect, test } from './test'

let fixture: MockBackendFixture | null = null

test.beforeAll(async () => {
  fixture = await setupMockBackend()
  await waitForAppReady(fixture, 120_000)
})

test.afterAll(async () => {
  await fixture?.cleanup()
  fixture = null
})

test('Stop stays available from the first send of a new chat onward', async () => {
  const page = fixture!.page
  const stop = page.getByRole('button', { name: 'Stop' }).first()

  const composer = page.locator('[contenteditable="true"]').first()
  await composer.click()
  await composer.type(`${PET_STALL_TRIGGER} first send`, { delay: 5 })
  await page.keyboard.press('Enter')

  await expect(stop).toBeVisible({ timeout: 10_000 })

  // Sample across the create → route re-home → agent build window.
  for (let i = 0; i < 25; i++) {
    expect(await stop.isVisible(), `Stop vanished ${i * 150}ms after it first appeared`).toBe(true)
    await page.waitForTimeout(150)
  }

  // The new chat's sidebar row shows it running, too.
  await expect(page.locator('[data-slot="sidebar"] [aria-label="Session running"]')).toHaveCount(1)

  await stop.click()
  await expect(stop).toBeHidden({ timeout: 15_000 })
})
