import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/headers', () => ({
  headers: vi.fn(async () => ({
    get: (k: string) => {
      if (k === 'x-vercel-forwarded-for') return '1.2.3.4'
      if (k === 'user-agent') return 'vitest'
      return null
    },
  })),
}))

const mockSupabase = {
  rpc: vi.fn(),
  auth: { signInWithPassword: vi.fn() },
}
vi.mock('@/lib/supabase/server', () => ({
  createClient: async () => mockSupabase,
}))

import { login } from '@/app/(auth)/_actions/auth'

beforeEach(() => {
  vi.useFakeTimers()
  mockSupabase.rpc.mockReset()
  mockSupabase.auth.signInWithPassword.mockReset()
})
afterEach(() => {
  vi.useRealTimers()
})

describe('login', () => {
  it('rate-limits at 10 per 15min via RPC', async () => {
    mockSupabase.rpc.mockResolvedValueOnce({ data: false })
    const p = login({ email: 'a@b.com', password: 'whatever' })
    await vi.advanceTimersByTimeAsync(1000)
    const r = await p
    expect(r).toEqual({ success: false, error: 'rate_limited' })
    expect(mockSupabase.auth.signInWithPassword).not.toHaveBeenCalled()
  })

  it('returns invalid_credentials on supabase error AND logs failure', async () => {
    mockSupabase.rpc
      .mockResolvedValueOnce({ data: true }) // rate limit OK
      .mockResolvedValueOnce({ data: null }) // log_auth_event
    mockSupabase.auth.signInWithPassword.mockResolvedValueOnce({
      error: { message: 'Invalid login credentials' },
      data: { user: null },
    })
    const p = login({ email: 'a@b.com', password: 'wrong' })
    await vi.advanceTimersByTimeAsync(1000)
    const r = await p
    expect(r).toEqual({ success: false, error: 'invalid_credentials' })
    expect(mockSupabase.rpc).toHaveBeenCalledWith(
      'log_auth_event',
      expect.objectContaining({
        p_event_type: 'login_failure',
      })
    )
  })

  it('returns success and logs login_success on happy path', async () => {
    mockSupabase.rpc
      .mockResolvedValueOnce({ data: true }) // rate limit
      .mockResolvedValueOnce({ data: null }) // log_auth_event
    mockSupabase.auth.signInWithPassword.mockResolvedValueOnce({
      error: null,
      data: { user: { id: 'user-123' }, session: { access_token: 'x' } },
    })
    const p = login({ email: 'a@b.com', password: 'Correct-Horse-99' })
    await vi.advanceTimersByTimeAsync(1000)
    const r = await p
    expect(r).toEqual({ success: true })
    expect(mockSupabase.rpc).toHaveBeenCalledWith(
      'log_auth_event',
      expect.objectContaining({
        p_event_type: 'login_success',
        p_user_id: 'user-123',
      })
    )
  })

  it('enforces 800ms floor on invalid_credentials', async () => {
    mockSupabase.rpc.mockResolvedValueOnce({ data: true }).mockResolvedValueOnce({ data: null })
    mockSupabase.auth.signInWithPassword.mockResolvedValueOnce({
      error: { message: 'X' },
      data: { user: null },
    })
    const p = login({ email: 'a@b.com', password: 'wrong' })
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
