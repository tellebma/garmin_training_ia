import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'

// Mock env so the real lib/worker (loaded by the action) can read WORKER_URL
// without hitting zod validation at module load.
vi.mock('@/lib/env', () => ({
  getServerEnv: () => ({ WORKER_URL: 'http://localhost:8080' }),
}))

const getSession = vi.fn()
vi.mock('@/lib/supabase/server', () => ({
  createClient: async () => ({ auth: { getSession } }),
}))

import { triggerGarminSync } from '@/app/actions/garmin-sync'

describe('triggerGarminSync', () => {
  beforeEach(() => {
    getSession.mockReset()
    getSession.mockResolvedValue({ data: { session: { access_token: 'jwt-123' } } })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('relays trigger and JWT to the worker and returns started', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200,
      json: async () => ({ status: 'started' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await triggerGarminSync('manual')

    expect(result).toEqual({ status: 'started' })
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8080/garmin/sync?trigger=manual',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ Authorization: 'Bearer jwt-123' }),
      })
    )
  })

  it('passes through a cooldown response', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200,
      json: async () => ({ status: 'cooldown', retry_after_seconds: 120 }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await triggerGarminSync('auto')

    expect(result).toEqual({ status: 'cooldown', retry_after_seconds: 120 })
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8080/garmin/sync?trigger=auto',
      expect.anything()
    )
  })

  it('throws when there is no session', async () => {
    getSession.mockResolvedValue({ data: { session: null } })
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    await expect(triggerGarminSync('manual')).rejects.toThrow('Not authenticated')
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
