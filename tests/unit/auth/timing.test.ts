import { describe, it, expect, vi } from 'vitest'
import { sleepUntil, AUTH_MIN_DURATION_MS } from '@/lib/auth/timing'

describe('sleepUntil', () => {
  it('returns immediately when target is in the past', async () => {
    const before = Date.now()
    await sleepUntil(before - 1000)
    const elapsed = Date.now() - before
    expect(elapsed).toBeLessThan(50)
  })

  it('waits until target is reached', async () => {
    const target = Date.now() + 50
    await sleepUntil(target)
    expect(Date.now()).toBeGreaterThanOrEqual(target - 5)
  })

  it('uses setTimeout under the hood', async () => {
    const spy = vi.spyOn(globalThis, 'setTimeout')
    await sleepUntil(Date.now() + 10)
    expect(spy).toHaveBeenCalled()
    spy.mockRestore()
  })
})

describe('AUTH_MIN_DURATION_MS', () => {
  it('is at least 500ms to defeat timing attacks', () => {
    expect(AUTH_MIN_DURATION_MS).toBeGreaterThanOrEqual(500)
  })
})
