import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/headers', () => ({
  headers: vi.fn(async () => ({
    get: (k: string) =>
      k === 'user-agent' ? 'vitest' : k === 'x-vercel-forwarded-for' ? '1.2.3.4' : null,
  })),
}))

vi.mock('next/navigation', () => ({
  redirect: vi.fn((path: string) => {
    throw new Error(`__NEXT_REDIRECT__:${path}`)
  }),
}))

const mockSupabase = {
  auth: { getUser: vi.fn(), updateUser: vi.fn() },
  from: vi.fn(),
  rpc: vi.fn(),
}
vi.mock('@/lib/supabase/server', () => ({
  createClient: async () => mockSupabase,
}))

import { setPasswordAfterReset } from '@/app/(auth)/_actions/auth'

beforeEach(() => {
  mockSupabase.auth.getUser.mockReset()
  mockSupabase.auth.updateUser.mockReset()
  mockSupabase.from.mockReset()
  mockSupabase.rpc.mockReset()
})

describe('setPasswordAfterReset', () => {
  const validInput = { password: 'New-Pass-2026!', confirm: 'New-Pass-2026!' }

  it('returns unauthenticated if no session', async () => {
    mockSupabase.auth.getUser.mockResolvedValueOnce({ data: { user: null } })
    const r = await setPasswordAfterReset(validInput)
    expect(r).toEqual({ success: false, error: 'unauthenticated' })
  })

  it('happy path : updateUser + flag + log + redirect /today', async () => {
    mockSupabase.auth.getUser.mockResolvedValueOnce({
      data: { user: { id: 'u1', email: 'a@b.com' } },
    })
    mockSupabase.from.mockReturnValueOnce({
      update: () => ({ eq: async () => ({ error: null }) }),
    })
    mockSupabase.auth.updateUser.mockResolvedValueOnce({ error: null })
    mockSupabase.rpc.mockResolvedValueOnce({ data: null })

    await expect(setPasswordAfterReset(validInput)).rejects.toThrow('__NEXT_REDIRECT__:/today')
    expect(mockSupabase.rpc).toHaveBeenCalledWith(
      'log_auth_event',
      expect.objectContaining({
        p_event_type: 'password_reset_completed',
      })
    )
  })

  it('rejects Zod fail (mismatch)', async () => {
    const r = await setPasswordAfterReset({ password: 'New-Pass-99!', confirm: 'Other-Pass-99!' })
    expect(r.success).toBe(false)
  })
})
