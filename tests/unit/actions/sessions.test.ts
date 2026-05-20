import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const workerEnsure = vi.fn()
const workerRegen = vi.fn()
const supabaseGetSession = vi.fn()

vi.mock('@/lib/worker', () => ({
  workerEnsureSessions: (jwt: string, days: number) => workerEnsure(jwt, days) as unknown,
  workerRegenerateSession: (jwt: string, id: string) => workerRegen(jwt, id) as unknown,
}))
vi.mock('@/lib/supabase/server', () => ({
  createClient: async () => ({
    auth: { getSession: () => supabaseGetSession() as unknown },
  }),
}))

describe('sessions Server Actions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })
  afterEach(() => vi.restoreAllMocks())

  it('ensureGeneratedSessions calls worker with current user JWT', async () => {
    supabaseGetSession.mockResolvedValueOnce({ data: { session: { access_token: 'jwt-1' } } })
    workerEnsure.mockResolvedValueOnce({ generated_count: 3 })
    const { ensureGeneratedSessions } = await import('@/app/actions/sessions')
    const result = await ensureGeneratedSessions(7)
    expect(workerEnsure).toHaveBeenCalledWith('jwt-1', 7)
    expect(result.success).toBe(true)
  })

  it('ensureGeneratedSessions returns error when unauthenticated', async () => {
    supabaseGetSession.mockResolvedValueOnce({ data: { session: null } })
    const { ensureGeneratedSessions } = await import('@/app/actions/sessions')
    const result = await ensureGeneratedSessions(7)
    expect(result.success).toBe(false)
  })

  it('regenerateSession calls worker with session id', async () => {
    supabaseGetSession.mockResolvedValueOnce({ data: { session: { access_token: 'jwt-1' } } })
    workerRegen.mockResolvedValueOnce({ status: 'ok', workout: { summary_md: 'x' } })
    const { regenerateSession } = await import('@/app/actions/sessions')
    const result = await regenerateSession('sess-1')
    expect(workerRegen).toHaveBeenCalledWith('jwt-1', 'sess-1')
    expect(result.success).toBe(true)
  })
})
