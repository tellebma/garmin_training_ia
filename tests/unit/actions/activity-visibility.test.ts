import { beforeEach, describe, expect, it, vi } from 'vitest'

const getSession = vi.fn()
const rpc = vi.fn()
const revalidatePath = vi.fn()
const workerRecomputeState = vi.fn()

vi.mock('next/cache', () => ({
  revalidatePath: (path: string) => revalidatePath(path) as unknown,
}))

vi.mock('@/lib/supabase/server', () => ({
  createClient: async () => ({ auth: { getSession }, rpc }),
}))

vi.mock('@/lib/worker', () => ({
  workerRecomputeState: (...args: unknown[]) => workerRecomputeState(...args) as unknown,
}))

const ACTIVITY_ID = '8f9dce34-c156-4b0f-90c2-ee55acb1d4b0'

describe('activity visibility actions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getSession.mockResolvedValue({
      data: { session: { user: { id: 'user-1' }, access_token: 'jwt-1' } },
    })
    rpc.mockResolvedValue({ error: null })
    workerRecomputeState.mockResolvedValue({ status: 'ok', days: 180 })
  })

  it('deletes an activity with its reason and refreshes every view it feeds', async () => {
    const { deleteActivity } = await import('@/app/actions/activity-visibility')

    const result = await deleteActivity({ activityId: ACTIVITY_ID, reason: 'doublon compteur' })

    expect(result).toEqual({ success: true, loadRecomputed: true })
    expect(workerRecomputeState).toHaveBeenCalledWith('jwt-1')
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

    expect(await restoreActivity(ACTIVITY_ID)).toEqual({ success: true, loadRecomputed: true })
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

  it('keeps the deletion when the load recompute fails', async () => {
    // Le worker peut être indisponible : la suppression reste acquise, le cron rattrapera.
    workerRecomputeState.mockRejectedValueOnce(new Error('worker down'))
    const { deleteActivity } = await import('@/app/actions/activity-visibility')

    expect(await deleteActivity({ activityId: ACTIVITY_ID, reason: null })).toEqual({
      success: true,
      loadRecomputed: false,
    })
  })

  it('reports a worker error status as a failed recompute', async () => {
    workerRecomputeState.mockResolvedValueOnce({
      status: 'unexpected_error',
      error_id: 'e1',
      type: 'RuntimeError',
    })
    const { deleteActivity } = await import('@/app/actions/activity-visibility')

    expect(await deleteActivity({ activityId: ACTIVITY_ID, reason: null })).toEqual({
      success: true,
      loadRecomputed: false,
    })
  })

  it('does not recompute when the exclusion itself failed', async () => {
    rpc.mockResolvedValueOnce({ error: { message: 'activity not found' } })
    const { deleteActivity } = await import('@/app/actions/activity-visibility')

    await deleteActivity({ activityId: ACTIVITY_ID, reason: null })

    expect(workerRecomputeState).not.toHaveBeenCalled()
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
