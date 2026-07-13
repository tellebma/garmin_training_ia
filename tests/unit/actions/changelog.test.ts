import { beforeEach, describe, expect, it, vi } from 'vitest'

const getSession = vi.fn()
const eq = vi.fn()
// Represents the resolved `{ data, error }` the Supabase chain yields once `.eq(...)`
// (the last call in the chain) is invoked — distinct from `profileQuery.update`, the
// query-builder method itself, which is asserted on separately below.
const updateResult = vi.fn()

const profileQuery = {
  update: vi.fn(),
  eq,
}
profileQuery.update.mockReturnValue(profileQuery)
profileQuery.eq.mockImplementation(() => updateResult() as unknown)

vi.mock('@/lib/supabase/server', () => ({
  createClient: async () => ({
    auth: { getSession },
    from: () => profileQuery,
  }),
}))

describe('markChangelogSeen', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getSession.mockResolvedValue({ data: { session: { user: { id: 'user-1' } } } })
    updateResult.mockResolvedValue({ error: null })
    profileQuery.update.mockReturnValue(profileQuery)
  })

  it('rejects an unauthenticated request', async () => {
    getSession.mockResolvedValueOnce({ data: { session: null } })
    const { markChangelogSeen } = await import('@/app/actions/changelog')

    await expect(markChangelogSeen('1.9.0')).resolves.toEqual({ success: false })
    expect(profileQuery.update).not.toHaveBeenCalled()
  })

  it('updates last_seen_changelog_version for the current user', async () => {
    const { markChangelogSeen } = await import('@/app/actions/changelog')

    await expect(markChangelogSeen('1.9.0')).resolves.toEqual({ success: true })
    expect(profileQuery.update).toHaveBeenCalledWith({ last_seen_changelog_version: '1.9.0' })
    expect(eq).toHaveBeenCalledWith('user_id', 'user-1')
  })

  it('returns success: false on a database error', async () => {
    updateResult.mockResolvedValueOnce({ error: { message: 'db unavailable' } })
    const { markChangelogSeen } = await import('@/app/actions/changelog')

    await expect(markChangelogSeen('1.9.0')).resolves.toEqual({ success: false })
  })
})
