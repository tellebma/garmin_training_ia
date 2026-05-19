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

import { setInitialPassword } from '@/app/(auth)/_actions/auth'

beforeEach(() => {
  mockSupabase.auth.getUser.mockReset()
  mockSupabase.auth.updateUser.mockReset()
  mockSupabase.from.mockReset()
  mockSupabase.rpc.mockReset()
})

describe('setInitialPassword', () => {
  const validInput = { password: 'M1ghty-Tr1@thlete', confirm: 'M1ghty-Tr1@thlete' }

  it('returns unauthenticated if no session', async () => {
    mockSupabase.auth.getUser.mockResolvedValueOnce({ data: { user: null } })
    const r = await setInitialPassword(validInput)
    expect(r).toEqual({ success: false, error: 'unauthenticated' })
  })

  it('I4 guard : refuses if password_set is already true', async () => {
    mockSupabase.auth.getUser.mockResolvedValueOnce({
      data: { user: { id: 'u1', email: 'a@b.com' } },
    })
    mockSupabase.from.mockReturnValueOnce({
      select: () => ({
        eq: () => ({
          single: async () => ({ data: { password_set: true } }),
        }),
      }),
    })
    const r = await setInitialPassword(validInput)
    expect(r).toEqual({ success: false, error: 'already_set' })
    expect(mockSupabase.auth.updateUser).not.toHaveBeenCalled()
  })

  it('happy path : updateUser + flag password_set=true + log + redirect /onboarding', async () => {
    mockSupabase.auth.getUser.mockResolvedValueOnce({
      data: { user: { id: 'u1', email: 'a@b.com' } },
    })
    mockSupabase.from
      .mockReturnValueOnce({
        select: () => ({
          eq: () => ({
            single: async () => ({ data: { password_set: false } }),
          }),
        }),
      })
      .mockReturnValueOnce({
        update: () => ({ eq: async () => ({ error: null }) }),
      })
    mockSupabase.auth.updateUser.mockResolvedValueOnce({ error: null })
    mockSupabase.rpc.mockResolvedValueOnce({ data: null })

    await expect(setInitialPassword(validInput)).rejects.toThrow('__NEXT_REDIRECT__:/onboarding')
    expect(mockSupabase.auth.updateUser).toHaveBeenCalledWith({ password: validInput.password })
    expect(mockSupabase.rpc).toHaveBeenCalledWith(
      'log_auth_event',
      expect.objectContaining({
        p_event_type: 'password_set',
        p_user_id: 'u1',
      })
    )
  })

  it("returns errors when Zod fails (passwords don't match)", async () => {
    const r = await setInitialPassword({
      password: 'M1ghty-Tr1@thlete',
      confirm: 'Different99-One!',
    })
    expect(r.success).toBe(false)
    if (!r.success && 'errors' in r) expect(r.errors).toBeDefined()
  })
})
