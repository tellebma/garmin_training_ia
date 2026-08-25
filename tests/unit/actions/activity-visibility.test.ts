import { beforeEach, describe, expect, it, vi } from 'vitest'

const getSession = vi.fn()
const rpc = vi.fn()
const revalidatePath = vi.fn()

vi.mock('next/cache', () => ({
  revalidatePath: (path: string) => revalidatePath(path) as unknown,
}))

vi.mock('@/lib/supabase/server', () => ({
  createClient: async () => ({ auth: { getSession }, rpc }),
}))

const ACTIVITY_ID = '8f9dce34-c156-4b0f-90c2-ee55acb1d4b0'

describe('activity visibility actions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getSession.mockResolvedValue({ data: { session: { user: { id: 'user-1' } } } })
    rpc.mockResolvedValue({ error: null })
  })

  it('deletes an activity with its reason and refreshes every view it feeds', async () => {
    const { deleteActivity } = await import('@/app/actions/activity-visibility')

    const result = await deleteActivity({ activityId: ACTIVITY_ID, reason: 'doublon compteur' })

    expect(result).toEqual({ success: true })
    expect(rpc).toHaveBeenCalledWith('set_activity_excluded', {
      p_activity_id: ACTIVITY_ID,
      p_excluded: true,
      p_reason: 'doublon compteur',
    })
    expect(revalidatePath.mock.calls.flat()).toEqual(
      expect.arrayContaining(['/history', '/stats', '/today'])
    )
  })

  it('turns an empty reason into null rather than an empty string', async () => {
    const { deleteActivity } = await import('@/app/actions/activity-visibility')

    await deleteActivity({ activityId: ACTIVITY_ID, reason: '   ' })

    expect(rpc).toHaveBeenCalledWith(
      'set_activity_excluded',
      expect.objectContaining({ p_reason: null })
    )
  })

  it('restores an activity', async () => {
    const { restoreActivity } = await import('@/app/actions/activity-visibility')

    expect(await restoreActivity(ACTIVITY_ID)).toEqual({ success: true })
    expect(rpc).toHaveBeenCalledWith('set_activity_excluded', {
      p_activity_id: ACTIVITY_ID,
      p_excluded: false,
      p_reason: null,
    })
  })

  it('validates the id before touching Supabase', async () => {
    const { deleteActivity, restoreActivity } = await import('@/app/actions/activity-visibility')

    expect(await deleteActivity({ activityId: 'nope', reason: null })).toEqual({
      success: false,
      error: 'invalid_input',
    })
    expect(await restoreActivity('nope')).toEqual({ success: false, error: 'invalid_input' })
    expect(getSession).not.toHaveBeenCalled()
  })

  it('refuses an unauthenticated caller', async () => {
    getSession.mockResolvedValueOnce({ data: { session: null } })
    const { deleteActivity } = await import('@/app/actions/activity-visibility')

    expect(await deleteActivity({ activityId: ACTIVITY_ID, reason: null })).toEqual({
      success: false,
      error: 'unauthenticated',
    })
    expect(rpc).not.toHaveBeenCalled()
  })

  it('surfaces an RPC failure', async () => {
    rpc.mockResolvedValueOnce({ error: { message: 'activity not found' } })
    const { deleteActivity } = await import('@/app/actions/activity-visibility')

    expect(await deleteActivity({ activityId: ACTIVITY_ID, reason: null })).toEqual({
      success: false,
      error: 'activity not found',
    })
  })
})
