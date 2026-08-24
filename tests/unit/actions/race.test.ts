import { beforeEach, describe, expect, it, vi } from 'vitest'

const getSession = vi.fn()
const rpc = vi.fn()
const upsert = vi.fn()
const maybeSingle = vi.fn()
const single = vi.fn()
const insert = vi.fn()
const revalidatePath = vi.fn()

const raceGoalsQuery = {
  select: vi.fn(),
  eq: vi.fn(),
  maybeSingle,
  insert,
  single,
}

vi.mock('next/cache', () => ({
  revalidatePath: (path: string) => revalidatePath(path) as unknown,
}))

vi.mock('@/lib/supabase/server', () => ({
  createClient: async () => ({
    auth: { getSession },
    rpc,
    from: (table: string) => (table === 'race_goals' ? raceGoalsQuery : { upsert }),
  }),
}))

/** `.single().overrideTypes()` : le mock doit répondre au dernier maillon de la chaîne. */
function singleResult(value: { data: unknown; error: unknown }) {
  return { overrideTypes: () => Promise.resolve(value) }
}

const ACTIVITY_ID = '8f9dce34-c156-4b0f-90c2-ee55acb1d4b0'
const RACE_ID = '2a6c2b7e-3f9f-4c0d-9c26-2a2fd7f6a111'

describe('race actions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    raceGoalsQuery.select.mockReturnValue(raceGoalsQuery)
    raceGoalsQuery.eq.mockReturnValue(raceGoalsQuery)
    raceGoalsQuery.insert.mockReturnValue(raceGoalsQuery)
    getSession.mockResolvedValue({ data: { session: { user: { id: 'user-1' } } } })
    rpc.mockResolvedValue({ error: null })
    upsert.mockResolvedValue({ error: null })
    maybeSingle.mockResolvedValue({ data: { id: RACE_ID }, error: null })
    single.mockReturnValue(singleResult({ data: { id: RACE_ID }, error: null }))
  })

  it('tags an activity through the RPC and revalidates the views', async () => {
    const { tagActivityAsRace } = await import('@/app/actions/race')

    const result = await tagActivityAsRace({ activityId: ACTIVITY_ID, raceGoalId: RACE_ID })

    expect(result).toEqual({ success: true, raceGoalId: RACE_ID })
    expect(rpc).toHaveBeenCalledWith('set_activity_race', {
      p_activity_id: ACTIVITY_ID,
      p_race_goal_id: RACE_ID,
    })
    expect(revalidatePath).toHaveBeenCalledWith(`/history/race/${RACE_ID}`)
  })

  it('validates before touching Supabase', async () => {
    const { tagActivityAsRace } = await import('@/app/actions/race')

    const result = await tagActivityAsRace({ activityId: 'nope', raceGoalId: RACE_ID })

    expect(result).toEqual({ success: false, error: 'invalid_input' })
    expect(getSession).not.toHaveBeenCalled()
  })

  it('refuses an unauthenticated tag', async () => {
    getSession.mockResolvedValueOnce({ data: { session: null } })
    const { tagActivityAsRace } = await import('@/app/actions/race')

    expect(await tagActivityAsRace({ activityId: ACTIVITY_ID, raceGoalId: RACE_ID })).toEqual({
      success: false,
      error: 'unauthenticated',
    })
  })

  it('surfaces an RPC failure', async () => {
    rpc.mockResolvedValueOnce({ error: { message: 'race goal not found' } })
    const { tagActivityAsRace } = await import('@/app/actions/race')

    expect(await tagActivityAsRace({ activityId: ACTIVITY_ID, raceGoalId: RACE_ID })).toEqual({
      success: false,
      error: 'race goal not found',
    })
  })

  it('untags an activity', async () => {
    const { untagActivityRace } = await import('@/app/actions/race')

    expect(await untagActivityRace(ACTIVITY_ID)).toEqual({ success: true })
    expect(rpc).toHaveBeenCalledWith('clear_activity_race', { p_activity_id: ACTIVITY_ID })
  })

  it('rejects an untag on a malformed id', async () => {
    const { untagActivityRace } = await import('@/app/actions/race')

    expect(await untagActivityRace('nope')).toEqual({ success: false, error: 'invalid_input' })
  })

  it('creates a retroactive race and links the activity to it', async () => {
    const { createRetroactiveRace } = await import('@/app/actions/race')

    const result = await createRetroactiveRace({
      activityId: ACTIVITY_ID,
      name: 'Premier triathlon',
      raceDate: '2026-08-22',
      discipline: 'triathlon',
      location: '',
    })

    expect(result).toEqual({ success: true, raceGoalId: RACE_ID })
    expect(insert).toHaveBeenCalledWith(
      expect.objectContaining({ is_primary: false, name: 'Premier triathlon', location: null })
    )
    expect(rpc).toHaveBeenCalledWith('set_activity_race', {
      p_activity_id: ACTIVITY_ID,
      p_race_goal_id: RACE_ID,
    })
  })

  it('reports an insert failure on the retroactive race', async () => {
    single.mockReturnValueOnce(singleResult({ data: null, error: { message: 'insert denied' } }))
    const { createRetroactiveRace } = await import('@/app/actions/race')

    expect(
      await createRetroactiveRace({
        activityId: ACTIVITY_ID,
        name: 'Course',
        raceDate: '2026-08-22',
        discipline: 'run',
        location: null,
      })
    ).toEqual({ success: false, error: 'insert denied' })
  })

  it('saves official results on a race the athlete owns', async () => {
    const { saveRaceResults } = await import('@/app/actions/race')

    const result = await saveRaceResults({
      raceGoalId: RACE_ID,
      officialTimeS: 9123,
      swimTimeS: 1800,
      t1TimeS: 200,
      bikeTimeS: 4200,
      t2TimeS: 100,
      runTimeS: 2700,
      overallRank: 42,
      overallFinishers: 310,
      category: 'S3',
      categoryRank: 5,
      categoryFinishers: 30,
      bibNumber: '187',
      resultsUrl: 'https://resultats.example.org/2026/tri',
      weather: '22 °C, vent',
      nutrition: '2 gels',
      gear: 'Combinaison',
      incidents: '',
      comment: 'Première ligne d’arrivée',
    })

    expect(result).toEqual({ success: true, raceGoalId: RACE_ID })
    expect(upsert).toHaveBeenCalledWith(
      expect.objectContaining({ official_time_s: 9123, incidents: null, user_id: 'user-1' }),
      { onConflict: 'race_goal_id' }
    )
  })

  it('refuses results on a race that is not the athlete’s', async () => {
    maybeSingle.mockResolvedValueOnce({ data: null, error: null })
    const { saveRaceResults } = await import('@/app/actions/race')

    expect(await saveRaceResults({ raceGoalId: RACE_ID, ...emptyResultsInput })).toEqual({
      success: false,
      error: 'race_not_found',
    })
  })

  it('rejects a results URL that is not http(s)', async () => {
    const { saveRaceResults } = await import('@/app/actions/race')

    expect(
      await saveRaceResults({
        raceGoalId: RACE_ID,
        ...emptyResultsInput,
        resultsUrl: 'javascript:alert(1)',
      })
    ).toEqual({ success: false, error: 'invalid_input' })
  })

  it('surfaces an upsert failure', async () => {
    upsert.mockResolvedValueOnce({ error: { message: 'write denied' } })
    const { saveRaceResults } = await import('@/app/actions/race')

    expect(await saveRaceResults({ raceGoalId: RACE_ID, ...emptyResultsInput })).toEqual({
      success: false,
      error: 'write denied',
    })
  })

  it('refuses unauthenticated results', async () => {
    getSession.mockResolvedValueOnce({ data: { session: null } })
    const { saveRaceResults } = await import('@/app/actions/race')

    expect(await saveRaceResults({ raceGoalId: RACE_ID, ...emptyResultsInput })).toEqual({
      success: false,
      error: 'unauthenticated',
    })
  })
})

const emptyResultsInput = {
  officialTimeS: null,
  swimTimeS: null,
  t1TimeS: null,
  bikeTimeS: null,
  t2TimeS: null,
  runTimeS: null,
  overallRank: null,
  overallFinishers: null,
  category: null,
  categoryRank: null,
  categoryFinishers: null,
  bibNumber: null,
  resultsUrl: null,
  weather: null,
  nutrition: null,
  gear: null,
  incidents: null,
  comment: null,
}
