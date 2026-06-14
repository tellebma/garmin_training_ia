import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const workerBriefing = vi.fn()
const supabaseGetSession = vi.fn()

const emptyActivityReview = {
  lookback_days: 90,
  activities_7d: 0,
  activities_28d: 0,
  tss_7d: 0,
  avg_weekly_tss_prev_21d: 0,
  elevation_gain_7d: 0,
  avg_weekly_elevation_prev_21d: 0,
  sport_counts_28d: {},
  days_since_last_activity: null,
  insights: [],
}

vi.mock('@/lib/worker', () => ({
  workerDailyBriefing: (jwt: string) => workerBriefing(jwt) as unknown,
}))
vi.mock('@/lib/supabase/server', () => ({
  createClient: async () => ({
    auth: { getSession: () => supabaseGetSession() as unknown },
  }),
}))

describe('getDailyBriefing', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })
  afterEach(() => vi.restoreAllMocks())

  it('returns briefing when worker responds with a full DailyBriefing', async () => {
    supabaseGetSession.mockResolvedValueOnce({ data: { session: { access_token: 'jwt-1' } } })
    workerBriefing.mockResolvedValueOnce({
      date: '2026-05-20',
      readiness_score: 78,
      status: 'ready',
      explanation_md: 'ok',
      factors: [],
      planned_session: null,
      suggested_session: null,
      activity_review: emptyActivityReview,
    })
    const { getDailyBriefing } = await import('@/app/actions/briefing')
    const r = await getDailyBriefing()
    expect(r.success).toBe(true)
    if (r.success) expect(r.briefing.readiness_score).toBe(78)
  })

  it('returns error when unauthenticated', async () => {
    supabaseGetSession.mockResolvedValueOnce({ data: { session: null } })
    const { getDailyBriefing } = await import('@/app/actions/briefing')
    const r = await getDailyBriefing()
    expect(r.success).toBe(false)
    if (!r.success) expect(r.error).toBe('unauthenticated')
  })

  it('returns error when worker says rate_limited', async () => {
    supabaseGetSession.mockResolvedValueOnce({ data: { session: { access_token: 'jwt-1' } } })
    workerBriefing.mockResolvedValueOnce({ status: 'rate_limited', retry_after_seconds: 60 })
    const { getDailyBriefing } = await import('@/app/actions/briefing')
    const r = await getDailyBriefing()
    expect(r.success).toBe(false)
    if (!r.success) expect(r.error).toBe('rate_limited')
  })

  it('returns error when worker throws', async () => {
    supabaseGetSession.mockResolvedValueOnce({ data: { session: { access_token: 'jwt-1' } } })
    workerBriefing.mockRejectedValueOnce(new Error('boom'))
    const { getDailyBriefing } = await import('@/app/actions/briefing')
    const r = await getDailyBriefing()
    expect(r.success).toBe(false)
  })

  it('returns unknown_response when worker returns unexpected shape', async () => {
    supabaseGetSession.mockResolvedValueOnce({ data: { session: { access_token: 'jwt-1' } } })
    // No "status" field and not a complete briefing -> fallthrough branch
    workerBriefing.mockResolvedValueOnce({ random: 'thing' })
    const { getDailyBriefing } = await import('@/app/actions/briefing')
    const r = await getDailyBriefing()
    expect(r.success).toBe(false)
    if (!r.success) expect(r.error).toBe('unknown_response')
  })
})
