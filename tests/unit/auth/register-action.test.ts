import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// Mock next/headers
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

// Mock supabase client
const mockSupabase = {
  rpc: vi.fn(),
  auth: { signInWithOtp: vi.fn() },
}
vi.mock('@/lib/supabase/server', () => ({
  createClient: async () => mockSupabase,
}))

import { registerWithMagicLink } from '@/app/(auth)/_actions/auth'

beforeEach(() => {
  vi.useFakeTimers()
  mockSupabase.rpc.mockReset()
  mockSupabase.auth.signInWithOtp.mockReset()
})

afterEach(() => {
  vi.useRealTimers()
})

async function advance(ms: number) {
  await vi.advanceTimersByTimeAsync(ms)
}

describe('registerWithMagicLink', () => {
  it('takes at least 800ms even on rate_limit short-circuit (C2 anti-timing)', async () => {
    mockSupabase.rpc.mockResolvedValueOnce({ data: false }) // rate limit blocks
    const p = registerWithMagicLink({ email: 'a@b.com' })
    await advance(799)
    let done = false
    void p.then(() => {
      done = true
    })
    await Promise.resolve()
    expect(done).toBe(false)
    await advance(2)
    await p
  })

  it('returns rate_limited when RPC returns false', async () => {
    mockSupabase.rpc.mockResolvedValueOnce({ data: false })
    const p = registerWithMagicLink({ email: 'a@b.com' })
    await vi.advanceTimersByTimeAsync(1000)
    const r = await p
    expect(r).toEqual({ success: false, error: 'rate_limited' })
    expect(mockSupabase.auth.signInWithOtp).not.toHaveBeenCalled()
  })

  it('returns email_not_allowed when is_email_allowed returns false', async () => {
    mockSupabase.rpc
      .mockResolvedValueOnce({ data: true }) // rate limit OK
      .mockResolvedValueOnce({ data: false }) // is_email_allowed false
    const p = registerWithMagicLink({ email: 'a@b.com' })
    await vi.advanceTimersByTimeAsync(1000)
    const r = await p
    expect(r).toEqual({ success: false, error: 'email_not_allowed' })
    expect(mockSupabase.auth.signInWithOtp).not.toHaveBeenCalled()
  })

  it('does NOT send OTP when email_needs_signup returns false (I3 anti-spam)', async () => {
    mockSupabase.rpc
      .mockResolvedValueOnce({ data: true }) // rate limit OK
      .mockResolvedValueOnce({ data: true }) // is_email_allowed true
      .mockResolvedValueOnce({ data: false }) // email_needs_signup false (déjà actif)
    const p = registerWithMagicLink({ email: 'a@b.com' })
    await vi.advanceTimersByTimeAsync(1000)
    const r = await p
    expect(r).toEqual({ success: true }) // generic success — pas de leak
    expect(mockSupabase.auth.signInWithOtp).not.toHaveBeenCalled()
  })

  it('sends OTP + logs audit on happy path', async () => {
    mockSupabase.rpc
      .mockResolvedValueOnce({ data: true }) // rate limit OK
      .mockResolvedValueOnce({ data: true }) // is_email_allowed
      .mockResolvedValueOnce({ data: true }) // email_needs_signup
      .mockResolvedValueOnce({ data: null }) // log_auth_event
    mockSupabase.auth.signInWithOtp.mockResolvedValueOnce({ error: null })
    const p = registerWithMagicLink({ email: 'a@b.com' })
    await vi.advanceTimersByTimeAsync(1000)
    const r = await p
    expect(r).toEqual({ success: true })
    expect(mockSupabase.auth.signInWithOtp).toHaveBeenCalledOnce()
    expect(mockSupabase.rpc).toHaveBeenCalledWith(
      'log_auth_event',
      expect.objectContaining({
        p_event_type: 'register_initiated',
      })
    )
  })

  it('rejects malformed email via Zod', async () => {
    const p = registerWithMagicLink({ email: 'not-an-email' })
    await vi.advanceTimersByTimeAsync(1000)
    const r = await p
    expect(r.success).toBe(false)
    if (!r.success && 'errors' in r) expect(r.errors).toBeDefined()
  })
})
