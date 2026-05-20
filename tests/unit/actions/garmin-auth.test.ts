import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const getSession = vi.fn()
const createClient = vi.fn(() =>
  Promise.resolve({
    auth: { getSession },
  })
)
const workerPost = vi.fn()

vi.mock('@/lib/supabase/server', () => ({
  createClient,
}))

vi.mock('@/lib/worker', () => ({
  workerPost,
}))

describe('connectGarmin (Server Action)', () => {
  beforeEach(() => {
    getSession.mockReset()
    workerPost.mockReset()
  })

  afterEach(() => {
    vi.resetModules()
  })

  it('throws when user has no session', async () => {
    getSession.mockResolvedValueOnce({ data: { session: null } })
    const { connectGarmin } = await import('@/app/actions/garmin-auth')
    await expect(connectGarmin('e@x.com', 'pw')).rejects.toThrow(/Not authenticated/)
    expect(workerPost).not.toHaveBeenCalled()
  })

  it('forwards email+password to the worker with bearer JWT', async () => {
    getSession.mockResolvedValueOnce({ data: { session: { access_token: 'jwt-abc' } } })
    workerPost.mockResolvedValueOnce({ status: 'connected' })
    const { connectGarmin } = await import('@/app/actions/garmin-auth')

    const result = await connectGarmin('user@example.com', 'secret')
    expect(result).toEqual({ status: 'connected' })
    expect(workerPost).toHaveBeenCalledWith(
      '/garmin/connect',
      { email: 'user@example.com', password: 'secret' },
      'jwt-abc'
    )
  })

  it('returns mfa_required when worker signals it', async () => {
    getSession.mockResolvedValueOnce({ data: { session: { access_token: 'jwt' } } })
    workerPost.mockResolvedValueOnce({ status: 'mfa_required', challenge_id: 'ch1' })
    const { connectGarmin } = await import('@/app/actions/garmin-auth')

    const result = await connectGarmin('u', 'p')
    expect(result).toEqual({ status: 'mfa_required', challenge_id: 'ch1' })
  })
})

describe('submitGarminMfa (Server Action)', () => {
  beforeEach(() => {
    getSession.mockReset()
    workerPost.mockReset()
  })

  it('throws when user has no session', async () => {
    getSession.mockResolvedValueOnce({ data: { session: null } })
    const { submitGarminMfa } = await import('@/app/actions/garmin-auth')
    await expect(submitGarminMfa('ch1', '123456')).rejects.toThrow(/Not authenticated/)
  })

  it('forwards challenge_id+code to the worker', async () => {
    getSession.mockResolvedValueOnce({ data: { session: { access_token: 'jwt-z' } } })
    workerPost.mockResolvedValueOnce({ status: 'connected' })
    const { submitGarminMfa } = await import('@/app/actions/garmin-auth')

    const result = await submitGarminMfa('challenge-xyz', '654321')
    expect(result).toEqual({ status: 'connected' })
    expect(workerPost).toHaveBeenCalledWith(
      '/garmin/mfa',
      { challenge_id: 'challenge-xyz', code: '654321' },
      'jwt-z'
    )
  })
})
