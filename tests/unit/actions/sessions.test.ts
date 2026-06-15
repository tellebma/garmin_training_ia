import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const workerEnsure = vi.fn()
const workerRegen = vi.fn()
const supabaseGetSession = vi.fn()
const supabaseFrom = vi.fn()
const revalidatePath = vi.fn()

vi.mock('@/lib/worker', () => ({
  workerEnsureSessions: (jwt: string, days: number) => workerEnsure(jwt, days) as unknown,
  workerRegenerateSession: (jwt: string, id: string) => workerRegen(jwt, id) as unknown,
}))
vi.mock('@/lib/supabase/server', () => ({
  createClient: async () => ({
    auth: { getSession: () => supabaseGetSession() as unknown },
    from: supabaseFrom,
  }),
}))
vi.mock('next/cache', () => ({
  revalidatePath: (path: string): void => {
    revalidatePath(path)
  },
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

  it('regenerateSession returns error when unauthenticated', async () => {
    supabaseGetSession.mockResolvedValueOnce({ data: { session: null } })
    const { regenerateSession } = await import('@/app/actions/sessions')
    const result = await regenerateSession('sess-1')
    expect(result.success).toBe(false)
  })

  it('ensureGeneratedSessions returns error when worker throws', async () => {
    supabaseGetSession.mockResolvedValueOnce({ data: { session: { access_token: 'jwt-1' } } })
    workerEnsure.mockRejectedValueOnce(new Error('worker down'))
    const { ensureGeneratedSessions } = await import('@/app/actions/sessions')
    const result = await ensureGeneratedSessions(7)
    expect(result.success).toBe(false)
    if (!result.success) expect(result.error).toBe('worker down')
  })

  it('regenerateSession returns error when worker throws', async () => {
    supabaseGetSession.mockResolvedValueOnce({ data: { session: { access_token: 'jwt-1' } } })
    workerRegen.mockRejectedValueOnce(new Error('boom'))
    const { regenerateSession } = await import('@/app/actions/sessions')
    const result = await regenerateSession('sess-1')
    expect(result.success).toBe(false)
    if (!result.success) expect(result.error).toBe('boom')
  })

  it('ensureGeneratedSessions surfaces rate_limited status as failure', async () => {
    supabaseGetSession.mockResolvedValueOnce({ data: { session: { access_token: 'jwt-1' } } })
    workerEnsure.mockResolvedValueOnce({ status: 'rate_limited', retry_after_seconds: 60 })
    const { ensureGeneratedSessions } = await import('@/app/actions/sessions')
    const result = await ensureGeneratedSessions(7)
    expect(result.success).toBe(false)
    if (!result.success) expect(result.error).toBe('rate_limited')
  })

  it('regenerateSession surfaces rate_limited status as failure', async () => {
    supabaseGetSession.mockResolvedValueOnce({ data: { session: { access_token: 'jwt-1' } } })
    workerRegen.mockResolvedValueOnce({ status: 'rate_limited', retry_after_seconds: 600 })
    const { regenerateSession } = await import('@/app/actions/sessions')
    const result = await regenerateSession('sess-1')
    expect(result.success).toBe(false)
    if (!result.success) expect(result.error).toBe('rate_limited')
  })

  it('regenerateSession surfaces session_not_found status as failure', async () => {
    supabaseGetSession.mockResolvedValueOnce({ data: { session: { access_token: 'jwt-1' } } })
    workerRegen.mockResolvedValueOnce({ status: 'session_not_found' })
    const { regenerateSession } = await import('@/app/actions/sessions')
    const result = await regenerateSession('sess-1')
    expect(result.success).toBe(false)
    if (!result.success) expect(result.error).toBe('session_not_found')
  })

  it('applySessionAdjustment updates the owned session and clears workout', async () => {
    supabaseGetSession.mockResolvedValueOnce({
      data: { session: { user: { id: 'u1' }, access_token: 'jwt-1' } },
    })
    const selectMaybeSingle = vi.fn().mockResolvedValueOnce({
      data: {
        id: 'sess-1',
        user_id: 'u1',
        session_type: 'intervals',
        target_duration_s: 3600,
        target_tss: 80,
      },
      error: null,
    })
    const selectEqUser = vi.fn(() => ({ maybeSingle: selectMaybeSingle }))
    const selectEqId = vi.fn(() => ({ eq: selectEqUser }))
    const selectQuery = {
      select: vi.fn(() => ({ eq: selectEqId })),
    }
    const updateEqUser = vi.fn().mockResolvedValueOnce({ error: null })
    const updateEqId = vi.fn(() => ({ eq: updateEqUser }))
    const updateQuery = {
      update: vi.fn(() => ({ eq: updateEqId })),
    }
    const upsertQuery = {
      upsert: vi.fn().mockResolvedValueOnce({ error: null }),
    }
    supabaseFrom
      .mockReturnValueOnce(selectQuery)
      .mockReturnValueOnce(updateQuery)
      .mockReturnValueOnce(upsertQuery)

    const { applySessionAdjustment } = await import('@/app/actions/sessions')
    const result = await applySessionAdjustment('sess-1', 'recovery')

    expect(result.success).toBe(true)
    expect(updateQuery.update).toHaveBeenCalledWith({
      session_type: 'recovery',
      workout: null,
      workout_generated_at: null,
      target_duration_s: 2400,
      target_tss: 30,
    })
    expect(updateEqId).toHaveBeenCalledWith('id', 'sess-1')
    expect(updateEqUser).toHaveBeenCalledWith('user_id', 'u1')
    expect(upsertQuery.upsert).toHaveBeenCalledWith(
      {
        user_id: 'u1',
        planned_session_id: 'sess-1',
        original_session_type: 'intervals',
        suggested_session_type: 'recovery',
        decision: 'accepted',
        source: 'daily_briefing',
      },
      { onConflict: 'user_id,planned_session_id,suggested_session_type' }
    )
    expect(revalidatePath).toHaveBeenCalledWith('/today')
    expect(revalidatePath).toHaveBeenCalledWith('/plan')
  })

  it('ignoreSessionAdjustment stores an ignored decision without changing the session', async () => {
    supabaseGetSession.mockResolvedValueOnce({
      data: { session: { user: { id: 'u1' }, access_token: 'jwt-1' } },
    })
    const selectMaybeSingle = vi.fn().mockResolvedValueOnce({
      data: { id: 'sess-1', user_id: 'u1', session_type: 'intervals' },
      error: null,
    })
    const selectEqUser = vi.fn(() => ({ maybeSingle: selectMaybeSingle }))
    const selectEqId = vi.fn(() => ({ eq: selectEqUser }))
    const selectQuery = {
      select: vi.fn(() => ({ eq: selectEqId })),
    }
    const upsertQuery = {
      upsert: vi.fn().mockResolvedValueOnce({ error: null }),
    }
    supabaseFrom.mockReturnValueOnce(selectQuery).mockReturnValueOnce(upsertQuery)

    const { ignoreSessionAdjustment } = await import('@/app/actions/sessions')
    const result = await ignoreSessionAdjustment('sess-1', 'recovery')

    expect(result.success).toBe(true)
    expect(upsertQuery.upsert).toHaveBeenCalledWith(
      {
        user_id: 'u1',
        planned_session_id: 'sess-1',
        original_session_type: 'intervals',
        suggested_session_type: 'recovery',
        decision: 'ignored',
        source: 'daily_briefing',
      },
      { onConflict: 'user_id,planned_session_id,suggested_session_type' }
    )
    expect(revalidatePath).toHaveBeenCalledWith('/today')
  })

  it('applySessionAdjustment rejects invalid session types', async () => {
    supabaseGetSession.mockResolvedValueOnce({
      data: { session: { user: { id: 'u1' }, access_token: 'jwt-1' } },
    })
    const { applySessionAdjustment } = await import('@/app/actions/sessions')
    const result = await applySessionAdjustment('sess-1', 'harder-than-needed')

    expect(result.success).toBe(false)
    if (!result.success) expect(result.error).toBe('invalid_session_type')
    expect(supabaseFrom).not.toHaveBeenCalled()
  })
})
