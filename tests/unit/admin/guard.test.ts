import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const getCurrentUser = vi.fn()
const rpc = vi.fn()

vi.mock('@/lib/supabase/current-user', () => ({
  getCurrentUser: (...args: unknown[]) => getCurrentUser(...args) as unknown,
}))

vi.mock('@/lib/supabase/server', () => ({
  createClient: () => Promise.resolve({ rpc }),
}))

const redirect = vi.fn((path: string) => {
  throw new Error(`__REDIRECT__:${path}`)
})
vi.mock('next/navigation', () => ({ redirect: (path: string) => redirect(path) }))

beforeEach(() => {
  getCurrentUser.mockReset()
  rpc.mockReset()
  redirect.mockClear()
})

afterEach(() => {
  vi.resetModules()
})

describe('requireAdmin', () => {
  it('redirects to /login when no user', async () => {
    getCurrentUser.mockResolvedValueOnce(null)
    const { requireAdmin } = await import('@/lib/admin/guard')
    await expect(requireAdmin()).rejects.toThrow(/__REDIRECT__:\/login/)
  })

  it('redirects to /today when the user is not an admin', async () => {
    getCurrentUser.mockResolvedValueOnce({ id: 'u1' })
    rpc.mockResolvedValueOnce({ data: false })
    const { requireAdmin } = await import('@/lib/admin/guard')
    await expect(requireAdmin()).rejects.toThrow(/__REDIRECT__:\/today/)
  })

  it('returns the user id when the user is an admin', async () => {
    getCurrentUser.mockResolvedValueOnce({ id: 'owner-id' })
    rpc.mockResolvedValueOnce({ data: true })
    const { requireAdmin } = await import('@/lib/admin/guard')
    await expect(requireAdmin()).resolves.toBe('owner-id')
  })
})
