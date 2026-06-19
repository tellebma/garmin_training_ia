import { beforeEach, describe, expect, it, vi } from 'vitest'

const getSession = vi.fn()
const maybeSingle = vi.fn()
const upsert = vi.fn()
const revalidatePath = vi.fn()

const activityQuery = {
  select: vi.fn(),
  eq: vi.fn(),
  maybeSingle,
}

activityQuery.select.mockReturnValue(activityQuery)
activityQuery.eq.mockReturnValue(activityQuery)

vi.mock('next/cache', () => ({
  revalidatePath: (path: string) => revalidatePath(path) as unknown,
}))

vi.mock('@/lib/supabase/server', () => ({
  createClient: async () => ({
    auth: { getSession },
    from: (table: string) => (table === 'activities' ? activityQuery : { upsert }),
  }),
}))

const validInput = {
  activityId: '8f9dce34-c156-4b0f-90c2-ee55acb1d4b0',
  rpe: 7,
  fatigue: 3,
  soreness: 2,
  pain: 0,
  mood: 4,
  perceivedDifficulty: 'as_expected' as const,
  painArea: '',
  comment: 'Bonnes sensations',
}

describe('saveActivityFeedback', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    activityQuery.select.mockReturnValue(activityQuery)
    activityQuery.eq.mockReturnValue(activityQuery)
    getSession.mockResolvedValue({ data: { session: { user: { id: 'user-1' } } } })
    maybeSingle.mockResolvedValue({ data: { id: validInput.activityId }, error: null })
    upsert.mockResolvedValue({ error: null })
  })

  it('validates before accessing Supabase', async () => {
    const { saveActivityFeedback } = await import('@/app/actions/activity-feedback')
    const result = await saveActivityFeedback({ ...validInput, rpe: 11 })

    expect(result).toEqual({ success: false, error: 'invalid_feedback' })
    expect(getSession).not.toHaveBeenCalled()
  })

  it('rejects an unauthenticated request', async () => {
    getSession.mockResolvedValueOnce({ data: { session: null } })
    const { saveActivityFeedback } = await import('@/app/actions/activity-feedback')

    await expect(saveActivityFeedback(validInput)).resolves.toEqual({
      success: false,
      error: 'unauthenticated',
    })
  })

  it('checks activity ownership before saving', async () => {
    maybeSingle.mockResolvedValueOnce({ data: null, error: null })
    const { saveActivityFeedback } = await import('@/app/actions/activity-feedback')

    await expect(saveActivityFeedback(validInput)).resolves.toEqual({
      success: false,
      error: 'activity_not_found',
    })
    expect(upsert).not.toHaveBeenCalled()
  })

  it('upserts normalized feedback and invalidates coach views', async () => {
    const { saveActivityFeedback } = await import('@/app/actions/activity-feedback')
    const result = await saveActivityFeedback(validInput)

    expect(result).toEqual({ success: true })
    expect(upsert).toHaveBeenCalledWith(
      expect.objectContaining({
        user_id: 'user-1',
        activity_id: validInput.activityId,
        rpe: 7,
        pain_area: null,
        comment: 'Bonnes sensations',
      }),
      { onConflict: 'user_id,activity_id' }
    )
    expect(revalidatePath).toHaveBeenCalledWith(`/history/${validInput.activityId}`)
    expect(revalidatePath).toHaveBeenCalledWith('/stats')
    expect(revalidatePath).toHaveBeenCalledWith('/today')
  })

  it('returns the database error', async () => {
    upsert.mockResolvedValueOnce({ error: { message: 'db unavailable' } })
    const { saveActivityFeedback } = await import('@/app/actions/activity-feedback')

    await expect(saveActivityFeedback(validInput)).resolves.toEqual({
      success: false,
      error: 'db unavailable',
    })
  })
})
