import { describe, expect, it } from 'vitest'
import { loadChangelog } from '@/lib/changelog/read'

describe('loadChangelog', () => {
  it('reads and parses docs/nouveautes.md from the repo root', async () => {
    const entries = await loadChangelog()
    expect(entries.length).toBeGreaterThanOrEqual(2)
    expect(entries[0]).toMatchObject({ version: '1.13.0', date: '2026-07-26' })
    expect(entries[0]?.bullets.length).toBeGreaterThan(0)
  })
})
