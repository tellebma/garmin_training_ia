import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

beforeAll(() => {
  process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co'
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'anon-key-test'
})

const getUser = vi.fn()
const fromMock = vi.fn()

vi.mock('@/lib/supabase/server', () => ({
  createClient: () =>
    Promise.resolve({
      auth: { getUser },
      from: (...args: unknown[]) => fromMock(...args) as unknown,
    }),
}))

const redirect = vi.fn((path: string) => {
  throw new Error(`__REDIRECT__:${path}`)
})
vi.mock('next/navigation', () => ({
  redirect: (path: string) => redirect(path),
}))

function mkSelect(data: { onboarding_completed_at: string | null } | null) {
  const single = vi.fn().mockResolvedValue({ data })
  const eq = vi.fn(() => ({ single }))
  return { select: vi.fn(() => ({ eq })) }
}

beforeEach(() => {
  getUser.mockReset()
  fromMock.mockReset()
  redirect.mockClear()
})

afterEach(() => {
  vi.resetModules()
})

describe('requireOnboarded', () => {
  it('redirects to /login when no user', async () => {
    getUser.mockResolvedValueOnce({ data: { user: null } })
    const { requireOnboarded } = await import('@/lib/onboarding/guard')
    await expect(requireOnboarded()).rejects.toThrow(/__REDIRECT__:\/login/)
  })

  it('redirects to /onboarding when onboarding not completed', async () => {
    getUser.mockResolvedValueOnce({ data: { user: { id: 'u1' } } })
    fromMock.mockReturnValueOnce(mkSelect({ onboarding_completed_at: null }))
    const { requireOnboarded } = await import('@/lib/onboarding/guard')
    await expect(requireOnboarded()).rejects.toThrow(/__REDIRECT__:\/onboarding/)
  })

  it('redirects to /onboarding when profile is null', async () => {
    getUser.mockResolvedValueOnce({ data: { user: { id: 'u1' } } })
    fromMock.mockReturnValueOnce(mkSelect(null))
    const { requireOnboarded } = await import('@/lib/onboarding/guard')
    await expect(requireOnboarded()).rejects.toThrow(/__REDIRECT__:\/onboarding/)
  })

  it('returns user.id when onboarding completed', async () => {
    getUser.mockResolvedValueOnce({ data: { user: { id: 'u1' } } })
    fromMock.mockReturnValueOnce(mkSelect({ onboarding_completed_at: '2026-01-15T12:00:00Z' }))
    const { requireOnboarded } = await import('@/lib/onboarding/guard')
    const userId = await requireOnboarded()
    expect(userId).toBe('u1')
    expect(redirect).not.toHaveBeenCalled()
  })
})
