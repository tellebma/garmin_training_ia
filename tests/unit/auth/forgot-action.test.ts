import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/headers', () => ({
  headers: vi.fn(async () => ({
    get: (k: string) => {
      if (k === 'x-vercel-forwarded-for') return '1.2.3.4'
      if (k === 'user-agent') return 'vitest'
      if (k === 'host') return 'localhost:3000'
      if (k === 'x-forwarded-proto') return 'http'
      return null
    },
  })),
}))

const mockSupabase = {
  rpc: vi.fn(),
  auth: { resetPasswordForEmail: vi.fn() },
}
vi.mock('@/lib/supabase/server', () => ({
  createClient: async () => mockSupabase,
}))

import { requestPasswordReset } from '@/app/(auth)/_actions/auth'

beforeEach(() => {
  vi.useFakeTimers()
  mockSupabase.rpc.mockReset()
  mockSupabase.auth.resetPasswordForEmail.mockReset()
})
afterEach(() => {
  vi.useRealTimers()
})

describe('requestPasswordReset', () => {
  it('returns generic success even when email is invalid (no leak)', async () => {
    const p = requestPasswordReset({ email: 'not-an-email' })
    await vi.advanceTimersByTimeAsync(1000)
    const r = await p
    expect(r).toEqual({ success: true })
    expect(mockSupabase.auth.resetPasswordForEmail).not.toHaveBeenCalled()
  })

  it('returns generic success when rate-limited (no leak)', async () => {
    mockSupabase.rpc.mockResolvedValueOnce({ data: false })
    const p = requestPasswordReset({ email: 'a@b.com' })
    await vi.advanceTimersByTimeAsync(1000)
    const r = await p
    expect(r).toEqual({ success: true })
    expect(mockSupabase.auth.resetPasswordForEmail).not.toHaveBeenCalled()
  })

  it('happy path : calls resetPasswordForEmail + logs', async () => {
    mockSupabase.rpc
      .mockResolvedValueOnce({ data: true }) // rate limit OK
      .mockResolvedValueOnce({ data: null }) // log_auth_event
    mockSupabase.auth.resetPasswordForEmail.mockResolvedValueOnce({ error: null })

    const p = requestPasswordReset({ email: 'a@b.com' })
    await vi.advanceTimersByTimeAsync(1000)
    const r = await p

    expect(r).toEqual({ success: true })
    expect(mockSupabase.auth.resetPasswordForEmail).toHaveBeenCalledWith(
      'a@b.com',
      expect.objectContaining({
        redirectTo: expect.stringContaining('/auth/callback?next=/auth/reset-password'),
      })
    )
    expect(mockSupabase.rpc).toHaveBeenCalledWith(
      'log_auth_event',
      expect.objectContaining({ p_event_type: 'password_reset_requested' })
    )
  })

  it('enforces 800ms floor', async () => {
    const p = requestPasswordReset({ email: 'not-an-email' })
    await vi.advanceTimersByTimeAsync(799)
    let done = false
    void p.then(() => {
      done = true
    })
    await Promise.resolve()
    expect(done).toBe(false)
    await vi.advanceTimersByTimeAsync(2)
    await p
  })
})
