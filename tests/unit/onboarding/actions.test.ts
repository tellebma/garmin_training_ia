import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

beforeAll(() => {
  process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co'
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'anon-key-test'
  process.env.WORKER_URL = 'https://worker.local'
})

// Mocks
const getUser = vi.fn()
const getSession = vi.fn()
const fromMock = vi.fn()

vi.mock('@/lib/supabase/server', () => ({
  createClient: () =>
    Promise.resolve({
      auth: { getUser, getSession },
      from: (...args: unknown[]) => fromMock(...args) as unknown,
    }),
}))

const revalidatePath = vi.fn()
vi.mock('next/cache', () => ({
  revalidatePath: (...args: unknown[]) => revalidatePath(...args) as unknown,
}))

const redirect = vi.fn((path: string) => {
  // Mimic Next.js redirect: throw a marker so calling code stops
  throw new Error(`__REDIRECT__:${path}`)
})
vi.mock('next/navigation', () => ({
  redirect: (path: string) => redirect(path),
}))

const workerPost = vi.fn()
vi.mock('@/lib/worker', () => ({
  workerPost: (...args: unknown[]) => workerPost(...args) as unknown,
}))

// Helper: chainable query builder used by Supabase JS
function mkUpdateChain(error: unknown = null) {
  const eq = vi.fn().mockResolvedValue({ error })
  return { update: vi.fn(() => ({ eq })), _eq: eq }
}

function mkInsertChain(error: unknown = null) {
  return { insert: vi.fn().mockResolvedValue({ error }) }
}

function mkSelectMaybeSingle(data: unknown = null) {
  const maybeSingle = vi.fn().mockResolvedValue({ data })
  const eq2 = vi.fn(() => ({ maybeSingle }))
  const eq1 = vi.fn(() => ({ eq: eq2 }))
  return { select: vi.fn(() => ({ eq: eq1 })), _maybeSingle: maybeSingle }
}

function mkSelectSingle(data: unknown = null) {
  const single = vi.fn().mockResolvedValue({ data })
  const eq = vi.fn(() => ({ single }))
  return { select: vi.fn(() => ({ eq })) }
}

beforeEach(() => {
  getUser.mockReset()
  getSession.mockReset()
  fromMock.mockReset()
  workerPost.mockReset()
  revalidatePath.mockReset()
  redirect.mockClear()
})

afterEach(() => {
  vi.resetModules()
})

describe('saveStepPerso', () => {
  it('rejects unauthenticated user', async () => {
    getUser.mockResolvedValueOnce({ data: { user: null } })
    const { saveStepPerso } = await import('@/app/(app)/onboarding/actions')
    const r = await saveStepPerso({
      first_name: 'Max',
      dob: '1990-01-01',
      sex: 'M',
      consent_data_processing: true,
    })
    expect(r).toEqual({ success: false, error: 'unauthenticated' })
  })

  it('returns errors when Zod parsing fails', async () => {
    const { saveStepPerso } = await import('@/app/(app)/onboarding/actions')
    const r = await saveStepPerso({
      first_name: '',
      dob: 'bad',
      sex: 'Z' as 'M',
      consent_data_processing: false,
    })
    expect(r.success).toBe(false)
    if (!r.success && 'errors' in r) {
      expect(Object.keys(r.errors).length).toBeGreaterThan(0)
    }
  })

  it('updates athlete_profiles row when valid', async () => {
    getUser.mockResolvedValueOnce({ data: { user: { id: 'u1' } } })
    const chain = mkUpdateChain(null)
    fromMock.mockReturnValueOnce(chain)
    const { saveStepPerso } = await import('@/app/(app)/onboarding/actions')

    const r = await saveStepPerso({
      first_name: 'Max',
      dob: '1990-01-01',
      sex: 'M',
      consent_data_processing: true,
    })
    expect(r).toEqual({ success: true, nextStep: 'race' })
    expect(fromMock).toHaveBeenCalledWith('athlete_profiles')
    expect(chain.update).toHaveBeenCalledTimes(1)
    expect(revalidatePath).toHaveBeenCalledWith('/onboarding')
  })

  it('returns save_failed when DB update errors', async () => {
    getUser.mockResolvedValueOnce({ data: { user: { id: 'u1' } } })
    fromMock.mockReturnValueOnce(mkUpdateChain({ message: 'rls denied' }))
    const { saveStepPerso } = await import('@/app/(app)/onboarding/actions')

    const r = await saveStepPerso({
      first_name: 'Max',
      dob: '1990-01-01',
      sex: 'M',
      consent_data_processing: true,
    })
    expect(r).toEqual({ success: false, error: 'save_failed' })
  })
})

describe('saveStepRace', () => {
  const VALID_RACE = {
    race_date: '2026-09-01',
    discipline: 'triathlon' as const,
    legs: [
      { order: 1, discipline: 'swim' as const, distance_km: 1.5, elevation_gain_m: 0 },
      { order: 2, discipline: 'bike' as const, distance_km: 40, elevation_gain_m: 400 },
      { order: 3, discipline: 'run' as const, distance_km: 10, elevation_gain_m: 100 },
    ],
  }

  it('inserts a new race when none exists', async () => {
    getUser.mockResolvedValueOnce({ data: { user: { id: 'u1' } } })
    fromMock.mockReturnValueOnce(mkSelectMaybeSingle(null))
    const inserter = mkInsertChain(null)
    fromMock.mockReturnValueOnce(inserter)
    const { saveStepRace } = await import('@/app/(app)/onboarding/actions')

    const r = await saveStepRace(VALID_RACE)
    expect(r).toEqual({ success: true, nextStep: 'perf' })
    expect(inserter.insert).toHaveBeenCalledTimes(1)
    const payload = inserter.insert.mock.calls[0]?.[0] as Record<string, unknown>
    expect(payload.total_distance_km).toBeCloseTo(51.5, 1)
    expect(payload.total_elevation_gain_m).toBe(500)
    expect(payload.is_primary).toBe(true)
  })

  it('updates the existing primary race', async () => {
    getUser.mockResolvedValueOnce({ data: { user: { id: 'u1' } } })
    fromMock.mockReturnValueOnce(mkSelectMaybeSingle({ id: 'race-1' }))
    const chain = mkUpdateChain(null)
    fromMock.mockReturnValueOnce(chain)
    const { saveStepRace } = await import('@/app/(app)/onboarding/actions')

    await saveStepRace(VALID_RACE)
    expect(chain.update).toHaveBeenCalledTimes(1)
  })
})

describe('saveStepPerf', () => {
  it('skips DB write when no field provided', async () => {
    getUser.mockResolvedValueOnce({ data: { user: { id: 'u1' } } })
    const { saveStepPerf } = await import('@/app/(app)/onboarding/actions')

    const r = await saveStepPerf({})
    expect(r).toEqual({ success: true, nextStep: 'dispo' })
    expect(fromMock).not.toHaveBeenCalled()
  })

  it('applies the partial patch when fields provided', async () => {
    getUser.mockResolvedValueOnce({ data: { user: { id: 'u1' } } })
    const chain = mkUpdateChain(null)
    fromMock.mockReturnValueOnce(chain)
    const { saveStepPerf } = await import('@/app/(app)/onboarding/actions')

    await saveStepPerf({ ftp_watts: 250 })
    expect(chain.update).toHaveBeenCalledWith({ ftp_watts: 250 })
  })
})

describe('saveStepDispo', () => {
  it('applies the dispo defaults when values undefined', async () => {
    getUser.mockResolvedValueOnce({ data: { user: { id: 'u1' } } })
    const chain = mkUpdateChain(null)
    fromMock.mockReturnValueOnce(chain)
    const { saveStepDispo } = await import('@/app/(app)/onboarding/actions')

    const r = await saveStepDispo({})
    expect(r).toEqual({ success: true, nextStep: null })
    expect(chain.update).toHaveBeenCalledTimes(1)
    const arg = chain.update.mock.calls[0]?.[0] as Record<string, unknown>
    expect(arg.available_days).toBeDefined()
    expect(arg.hours_per_week).toBeDefined()
    expect(arg.sports_strengths).toBeDefined()
  })
})

describe('syncGarminProfile', () => {
  it('returns unauth marker when user missing', async () => {
    getUser.mockResolvedValueOnce({ data: { user: null } })
    const { syncGarminProfile } = await import('@/app/(app)/onboarding/actions')
    const r = await syncGarminProfile()
    expect(r.status).toBe('unexpected_error')
  })

  it('calls worker /garmin/profile-sync with bearer JWT', async () => {
    getUser.mockResolvedValueOnce({ data: { user: { id: 'u1' } } })
    getSession.mockResolvedValueOnce({ data: { session: { access_token: 'jwt-z' } } })
    workerPost.mockResolvedValueOnce({ status: 'ok', fetched: { ftp_watts: 240 } })
    const { syncGarminProfile } = await import('@/app/(app)/onboarding/actions')

    const r = await syncGarminProfile()
    expect(r).toMatchObject({ status: 'ok' })
    expect(workerPost).toHaveBeenCalledWith('/garmin/profile-sync', {}, 'jwt-z')
  })

  it('returns no_session marker when getSession is null after getUser', async () => {
    getUser.mockResolvedValueOnce({ data: { user: { id: 'u1' } } })
    getSession.mockResolvedValueOnce({ data: { session: null } })
    const { syncGarminProfile } = await import('@/app/(app)/onboarding/actions')
    const r = await syncGarminProfile()
    expect(r.status).toBe('unexpected_error')
  })
})

describe('finalizeOnboarding', () => {
  it('redirects to /login when not authenticated', async () => {
    getUser.mockResolvedValueOnce({ data: { user: null } })
    const { finalizeOnboarding } = await import('@/app/(app)/onboarding/actions')
    await expect(finalizeOnboarding()).rejects.toThrow(/__REDIRECT__:\/login/)
  })

  it('redirects to /onboarding when profile incomplete', async () => {
    getUser.mockResolvedValueOnce({ data: { user: { id: 'u1' } } })
    fromMock.mockReturnValueOnce(
      mkSelectSingle({
        first_name: null,
        dob: null,
        sex: null,
        consent_data_processing: false,
      })
    )
    fromMock.mockReturnValueOnce(mkSelectMaybeSingle(null))
    const { finalizeOnboarding } = await import('@/app/(app)/onboarding/actions')
    await expect(finalizeOnboarding()).rejects.toThrow(/__REDIRECT__:\/onboarding/)
  })

  it('completes and redirects to /profile when all data present', async () => {
    getUser.mockResolvedValueOnce({ data: { user: { id: 'u1' } } })
    fromMock.mockReturnValueOnce(
      mkSelectSingle({
        first_name: 'Max',
        dob: '1990-01-01',
        sex: 'M',
        consent_data_processing: true,
      })
    )
    fromMock.mockReturnValueOnce(mkSelectMaybeSingle({ id: 'race-1' }))
    const chain = mkUpdateChain(null)
    fromMock.mockReturnValueOnce(chain)
    const { finalizeOnboarding } = await import('@/app/(app)/onboarding/actions')

    await expect(finalizeOnboarding()).rejects.toThrow(/__REDIRECT__:\/profile\?onboarded=1/)
    expect(chain.update).toHaveBeenCalledWith(
      expect.objectContaining({ onboarding_completed_at: expect.any(String) })
    )
  })
})
