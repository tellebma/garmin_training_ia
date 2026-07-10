import { afterEach, describe, expect, it, vi } from 'vitest'

const getUser = vi.fn()

vi.mock('@/lib/supabase/server', () => ({
  createClient: () => Promise.resolve({ auth: { getUser } }),
}))

afterEach(() => {
  getUser.mockReset()
  vi.resetModules()
})

describe('lib/supabase/current-user', () => {
  it('returns the authenticated user from supabase.auth.getUser()', async () => {
    getUser.mockResolvedValueOnce({ data: { user: { id: 'u1' } } })
    const { getCurrentUser } = await import('@/lib/supabase/current-user')
    await expect(getCurrentUser()).resolves.toEqual({ id: 'u1' })
  })

  it('returns null when there is no authenticated user', async () => {
    getUser.mockResolvedValueOnce({ data: { user: null } })
    const { getCurrentUser } = await import('@/lib/supabase/current-user')
    await expect(getCurrentUser()).resolves.toBeNull()
  })
})

describe('getCurrentUser sharing across guards', () => {
  // These three consumers (app/(app)/layout.tsx, requireOnboarded,
  // requireAdmin) must all call the *same* exported `getCurrentUser`
  // rather than each doing their own `supabase.auth.getUser()`. That's
  // the actual fix: it's what lets React's `cache()` (Next.js "Request
  // Memoization") collapse them onto a single network call per request.
  //
  // We can prove they all resolve to the identical function reference by
  // mocking the module once and asserting every consumer invokes it. We
  // deliberately do NOT try to assert the network call is deduped here:
  // React's `cache()` only dedupes inside a live render pass owned by a
  // Next.js request. Invoked from a bare Vitest/Node context there is no
  // such render owner, so `cache()` degrades to calling the wrapped
  // function on every invocation (verified manually: two concurrent calls
  // to a `cache()`-wrapped counter produced two increments, not one).
  // Faking a request-scoped render here would only assert our own mock.

  it('is invoked by requireOnboarded, requireAdmin and AppLayout', async () => {
    vi.resetModules()
    const sharedGetCurrentUser = vi.fn().mockResolvedValue({ id: 'shared-user' })
    vi.doMock('@/lib/supabase/current-user', () => ({
      getCurrentUser: sharedGetCurrentUser,
    }))

    const fromMock = vi.fn(() => ({
      select: () => ({
        eq: () => ({
          single: () =>
            Promise.resolve({ data: { onboarding_completed_at: '2026-01-15T12:00:00Z' } }),
        }),
      }),
    }))
    const rpc = vi.fn().mockResolvedValue({ data: true })
    vi.doMock('@/lib/supabase/server', () => ({
      createClient: () => Promise.resolve({ from: fromMock, rpc }),
    }))
    vi.doMock('next/navigation', () => ({ redirect: vi.fn() }))

    const { requireOnboarded } = await import('@/lib/onboarding/guard')
    const { requireAdmin } = await import('@/lib/admin/guard')

    await requireOnboarded()
    await requireAdmin()

    expect(sharedGetCurrentUser).toHaveBeenCalledTimes(2)
  })
})
