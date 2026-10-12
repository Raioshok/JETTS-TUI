/**
 * E2E: the pet keeps you posted on your sessions (Codex-pets style).
 *
 * With a pet installed and enabled, one session is left working (the mock
 * never answers it) and another blocks on a clarify question. From a fresh
 * draft, the pet's card stack must list both — "needs you" first — and
 * clicking a card must open that session, which then drops out of the stack
 * (you're looking at it).
 *
 * Prerequisite: `npm run build` must have been run so dist/ exists.
 */

import fs from 'node:fs'
import path from 'node:path'
import zlib from 'node:zlib'

import type { Page } from '@playwright/test'

import { type MockBackendFixture, setupMockBackend, waitForAppReady } from './fixtures'
import { BLOCKING_CLARIFY_QUESTION, BLOCKING_CLARIFY_TRIGGER, PET_STALL_TRIGGER } from './mock-server'
import { expect, test } from './test'

const PET_SLUG = 'e2e-pet'

// ─── A tiny real spritesheet (8×9 cells of 192×208) ─────────────────────

function crc32(buf: Buffer): number {
  let c = ~0

  for (const byte of buf) {
    c ^= byte

    for (let k = 0; k < 8; k++) {
      c = c & 1 ? (c >>> 1) ^ 0xedb88320 : c >>> 1
    }
  }

  return ~c >>> 0
}

function pngChunk(type: string, data: Buffer): Buffer {
  const len = Buffer.alloc(4)
  len.writeUInt32BE(data.length)
  const body = Buffer.concat([Buffer.from(type, 'ascii'), data])
  const crc = Buffer.alloc(4)
  crc.writeUInt32BE(crc32(body))

  return Buffer.concat([len, body, crc])
}

/** Every cell gets an opaque rounded blob, so the sprite is visible and
 *  every row reports frames. */
function spritesheetPng(): Buffer {
  const cellW = 192
  const cellH = 208
  const width = cellW * 8
  const height = cellH * 9
  const raw = Buffer.alloc((width * 4 + 1) * height)

  for (let y = 0; y < height; y++) {
    const row = y * (width * 4 + 1)
    const cy = (y % cellH) - cellH / 2

    for (let x = 0; x < width; x++) {
      const cx = (x % cellW) - cellW / 2

      if ((cx / 70) ** 2 + (cy / 80) ** 2 <= 1) {
        raw.set([240, 150, 60, 255], row + 1 + x * 4)
      }
    }
  }

  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(width, 0)
  ihdr.writeUInt32BE(height, 4)
  ihdr[8] = 8 // bit depth
  ihdr[9] = 6 // RGBA

  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    pngChunk('IHDR', ihdr),
    pngChunk('IDAT', zlib.deflateSync(raw)),
    pngChunk('IEND', Buffer.alloc(0))
  ])
}

function installPet(jettstuiHome: string): void {
  const dir = path.join(jettstuiHome, 'pets', PET_SLUG)
  fs.mkdirSync(dir, { recursive: true })
  fs.writeFileSync(
    path.join(dir, 'pet.json'),
    JSON.stringify({ description: 'e2e', displayName: 'E2E Pet', id: PET_SLUG, spritesheetPath: 'spritesheet.png' })
  )
  fs.writeFileSync(path.join(dir, 'spritesheet.png'), spritesheetPng())
}

// ────────────────────────────────────────────────────────────────────────

let fixture: MockBackendFixture | null = null

test.beforeAll(async () => {
  fixture = await setupMockBackend({
    extraDisplayConfig: `  pet:\n    enabled: true\n    slug: ${PET_SLUG}`
  })
  installPet(fixture.sandbox.jettstuiHome)
  await waitForAppReady(fixture, 120_000)
})

test.afterAll(async () => {
  await fixture?.cleanup()
  fixture = null
})

async function send(page: Page, text: string): Promise<void> {
  const composer = page.locator('[contenteditable="true"]:visible').last()
  await composer.waitFor({ state: 'visible', timeout: 15_000 })
  await composer.click()
  await composer.type(text, { delay: 10 })
  await page.keyboard.press('Enter')
}

async function newSession(page: Page): Promise<void> {
  await page.locator('[data-slot="sidebar"] button[aria-label="New session"]').first().click()
  // A fresh draft has an empty transcript (the busy session keeps running).
  await expect(page.locator('[data-slot="aui_thread-viewport"]').last()).not.toContainText('E2E_', { timeout: 10_000 })
}

test('the pet lists working and waiting sessions and opens one on click', async () => {
  const page = fixture!.page
  const feed = page.getByRole('list', { name: 'Active sessions' })
  const rows = feed.getByRole('listitem')

  // Session 1: the model never answers → stays working.
  await send(page, `${PET_STALL_TRIGGER} first`)
  await expect(page.getByRole('button', { name: 'Stop' }).first()).toBeVisible({ timeout: 30_000 })

  // Session 2: blocks on a clarify question → needs you.
  await newSession(page)
  await send(page, BLOCKING_CLARIFY_TRIGGER)
  await expect(page.getByText(BLOCKING_CLARIFY_QUESTION).first()).toBeVisible({ timeout: 30_000 })

  // While session 2 is on screen, the pet only reports the *other* session.
  await expect(rows).toHaveCount(1, { timeout: 15_000 })
  await expect(rows.first()).toHaveAttribute('data-pet-session-row', 'working')

  // From a fresh draft, both show — the one waiting on you first.
  await newSession(page)
  await expect(rows).toHaveCount(2, { timeout: 15_000 })
  await expect(rows.nth(0)).toHaveAttribute('data-pet-session-row', 'needs-input')
  await expect(rows.nth(0)).toContainText('needs you')
  await expect(rows.nth(1)).toHaveAttribute('data-pet-session-row', 'working')
  await expect(rows.nth(1)).toContainText(/working · \d+[smh]/)
  await page.screenshot({ path: test.info().outputPath('pet-session-feed.png') })

  // Clicking the working card opens that session; it leaves the stack.
  await rows.nth(1).click()
  await expect(page.getByText(`${PET_STALL_TRIGGER} first`).last()).toBeVisible({ timeout: 10_000 })
  await expect(rows).toHaveCount(1)
  await expect(rows.first()).toHaveAttribute('data-pet-session-row', 'needs-input')
})
