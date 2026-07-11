import { beforeEach, describe, expect, it, vi } from 'vitest'

const getSession = vi.fn()
vi.mock('@/lib/supabase/server', () => ({
  createClient: () =>
    Promise.resolve({
      auth: {
        // eslint-disable-next-line @typescript-eslint/no-unsafe-return
        getSession: (...a: unknown[]) => getSession(...a),
      },
    }),
}))

const workerStravaConnect = vi.fn()
const workerStravaDisconnect = vi.fn()
vi.mock('@/lib/worker', () => ({
  workerStravaConnect: (...a: unknown[]) => workerStravaConnect(...a) as unknown,
  workerStravaDisconnect: (...a: unknown[]) => workerStravaDisconnect(...a) as unknown,
}))

import { connectStrava, disconnectStrava } from '@/app/actions/strava-auth'

beforeEach(() => {
  getSession.mockReset()
  workerStravaConnect.mockReset()
  workerStravaDisconnect.mockReset()
})

describe('connectStrava', () => {
  it('forwards the session JWT and code to the worker', async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: 'jwt-1' } } })
    workerStravaConnect.mockResolvedValue({ status: 'connected' })

    const result = await connectStrava('code-1')

    expect(workerStravaConnect).toHaveBeenCalledWith('jwt-1', 'code-1')
    expect(result).toEqual({ status: 'connected' })
  })

  it('throws when there is no session', async () => {
    getSession.mockResolvedValue({ data: { session: null } })

    await expect(connectStrava('code-1')).rejects.toThrow('Not authenticated')
  })
})

describe('disconnectStrava', () => {
  it('forwards the session JWT to the worker', async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: 'jwt-1' } } })
    workerStravaDisconnect.mockResolvedValue({ status: 'disconnected' })

    const result = await disconnectStrava()

    expect(workerStravaDisconnect).toHaveBeenCalledWith('jwt-1')
    expect(result).toEqual({ status: 'disconnected' })
  })
})
