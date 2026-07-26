import { describe, expect, it } from 'vitest'
import { loadChangelog } from '@/lib/changelog/read'

describe('loadChangelog', () => {
  // Asserts the shape of the real file rather than pinning its newest version:
  // every user-visible change adds an entry on top, and pinning would make each
  // one fail this test. parse.test.ts covers the parsing rules on fixtures.
  it('reads and parses docs/nouveautes.md from the repo root', async () => {
    const entries = await loadChangelog()
    expect(entries.length).toBeGreaterThanOrEqual(2)
    expect(entries[0]?.version).toMatch(/^\d+\.\d+\.\d+$/)
    expect(entries[0]?.date).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    expect(entries[0]?.bullets.length).toBeGreaterThan(0)
  })
})
