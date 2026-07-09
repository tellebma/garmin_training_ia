import { describe, expect, it } from 'vitest'
import {
  personSchema,
  raceSchema,
  perfSchema,
  dispoSchema,
  DISPO_DEFAULTS,
  computeTotals,
} from '@/lib/onboarding/schemas'

describe('personSchema', () => {
  const valid = {
    first_name: 'Maxime',
    dob: '1990-04-12',
    sex: 'M' as const,
    consent_data_processing: true,
  }

  it('accepts a valid minimal payload', () => {
    expect(personSchema.safeParse(valid).success).toBe(true)
  })

  it('rejects empty first_name', () => {
    expect(personSchema.safeParse({ ...valid, first_name: '' }).success).toBe(false)
  })

  it('rejects future dob', () => {
    expect(personSchema.safeParse({ ...valid, dob: '2999-01-01' }).success).toBe(false)
  })

  it('requires consent=true', () => {
    expect(personSchema.safeParse({ ...valid, consent_data_processing: false }).success).toBe(false)
  })

  it('rejects invalid sex value', () => {
    expect(personSchema.safeParse({ ...valid, sex: 'Z' }).success).toBe(false)
  })
})

describe('raceSchema', () => {
  const future = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10)

  const triathlonValid = {
    race_date: future,
    discipline: 'triathlon' as const,
    legs: [
      { order: 1, discipline: 'swim' as const, distance_km: 1.4, elevation_gain_m: 0 },
      { order: 2, discipline: 'bike' as const, distance_km: 53, elevation_gain_m: 2200 },
      { order: 3, discipline: 'run' as const, distance_km: 8, elevation_gain_m: 200 },
    ],
  }

  it('accepts a valid triathlon with 3 legs in correct order', () => {
    expect(raceSchema.safeParse(triathlonValid).success).toBe(true)
  })

  it('rejects triathlon with 2 legs', () => {
    const bad = { ...triathlonValid, legs: triathlonValid.legs.slice(0, 2) }
    expect(raceSchema.safeParse(bad).success).toBe(false)
  })

  it('rejects triathlon with wrong leg sequence (bike first)', () => {
    const bad = {
      ...triathlonValid,
      legs: [
        { order: 1, discipline: 'bike' as const, distance_km: 53, elevation_gain_m: 2200 },
        { order: 2, discipline: 'swim' as const, distance_km: 1.4, elevation_gain_m: 0 },
        { order: 3, discipline: 'run' as const, distance_km: 8, elevation_gain_m: 200 },
      ],
    }
    expect(raceSchema.safeParse(bad).success).toBe(false)
  })

  it('rejects past race_date', () => {
    const bad = { ...triathlonValid, race_date: '2000-01-01' }
    expect(raceSchema.safeParse(bad).success).toBe(false)
  })

  it('accepts run with 1 leg', () => {
    const ok = {
      race_date: future,
      discipline: 'run' as const,
      legs: [{ order: 1, discipline: 'run' as const, distance_km: 25, elevation_gain_m: 1000 }],
    }
    expect(raceSchema.safeParse(ok).success).toBe(true)
  })

  it('rejects run with a bike leg', () => {
    const bad = {
      race_date: future,
      discipline: 'run' as const,
      legs: [{ order: 1, discipline: 'bike' as const, distance_km: 25, elevation_gain_m: 1000 }],
    }
    expect(raceSchema.safeParse(bad).success).toBe(false)
  })

  it('accepts duathlon with run/bike/run sequence', () => {
    const ok = {
      race_date: future,
      discipline: 'duathlon' as const,
      legs: [
        { order: 1, discipline: 'run' as const, distance_km: 5, elevation_gain_m: 50 },
        { order: 2, discipline: 'bike' as const, distance_km: 20, elevation_gain_m: 300 },
        { order: 3, discipline: 'run' as const, distance_km: 2.5, elevation_gain_m: 30 },
      ],
    }
    expect(raceSchema.safeParse(ok).success).toBe(true)
  })

  it('accepts aquathlon with swim/run sequence', () => {
    const ok = {
      race_date: future,
      discipline: 'aquathlon' as const,
      legs: [
        { order: 1, discipline: 'swim' as const, distance_km: 1.5, elevation_gain_m: 0 },
        { order: 2, discipline: 'run' as const, distance_km: 5, elevation_gain_m: 50 },
      ],
    }
    expect(raceSchema.safeParse(ok).success).toBe(true)
  })

  it('accepts autre with 4 mixed legs (swimrun style)', () => {
    const ok = {
      race_date: future,
      discipline: 'autre' as const,
      legs: [
        { order: 1, discipline: 'swim' as const, distance_km: 0.5, elevation_gain_m: 0 },
        { order: 2, discipline: 'run' as const, distance_km: 3, elevation_gain_m: 50 },
        { order: 3, discipline: 'swim' as const, distance_km: 0.8, elevation_gain_m: 0 },
        { order: 4, discipline: 'run' as const, distance_km: 5, elevation_gain_m: 100 },
      ],
    }
    expect(raceSchema.safeParse(ok).success).toBe(true)
  })

  it('rejects autre with 11 legs (max 10)', () => {
    const tooMany = {
      race_date: future,
      discipline: 'autre' as const,
      legs: Array.from({ length: 11 }, (_, i) => ({
        order: i + 1,
        discipline: 'run' as const,
        distance_km: 1,
        elevation_gain_m: 0,
      })),
    }
    expect(raceSchema.safeParse(tooMany).success).toBe(false)
  })

  it('rejects non-sequential leg orders', () => {
    const bad = {
      race_date: future,
      discipline: 'autre' as const,
      legs: [
        { order: 1, discipline: 'run' as const, distance_km: 5, elevation_gain_m: 50 },
        { order: 3, discipline: 'run' as const, distance_km: 5, elevation_gain_m: 50 },
      ],
    }
    expect(raceSchema.safeParse(bad).success).toBe(false)
  })

  it('rejects distance <= 0', () => {
    const bad = {
      race_date: future,
      discipline: 'run' as const,
      legs: [{ order: 1, discipline: 'run' as const, distance_km: 0, elevation_gain_m: 0 }],
    }
    expect(raceSchema.safeParse(bad).success).toBe(false)
  })

  it('rejects D+ < 0', () => {
    const bad = {
      race_date: future,
      discipline: 'run' as const,
      legs: [{ order: 1, discipline: 'run' as const, distance_km: 5, elevation_gain_m: -10 }],
    }
    expect(raceSchema.safeParse(bad).success).toBe(false)
  })

  it('rejects D+ > 20000', () => {
    const bad = {
      race_date: future,
      discipline: 'run' as const,
      legs: [{ order: 1, discipline: 'run' as const, distance_km: 5, elevation_gain_m: 25000 }],
    }
    expect(raceSchema.safeParse(bad).success).toBe(false)
  })
})

describe('computeTotals', () => {
  it('sums Triathlon Madeleine correctly (62.4 km, 2400 m)', () => {
    const legs = [
      { order: 1, discipline: 'swim' as const, distance_km: 1.4, elevation_gain_m: 0 },
      { order: 2, discipline: 'bike' as const, distance_km: 53, elevation_gain_m: 2200 },
      { order: 3, discipline: 'run' as const, distance_km: 8, elevation_gain_m: 200 },
    ]
    expect(computeTotals(legs)).toEqual({
      total_distance_km: 62.4,
      total_elevation_gain_m: 2400,
    })
  })

  it('sums a mono-leg trail (25 km / 1000 m)', () => {
    const legs = [{ order: 1, discipline: 'run' as const, distance_km: 25, elevation_gain_m: 1000 }]
    expect(computeTotals(legs)).toEqual({
      total_distance_km: 25,
      total_elevation_gain_m: 1000,
    })
  })

  it('rounds distance to 2 decimals', () => {
    const legs = [
      { order: 1, discipline: 'run' as const, distance_km: 1.234, elevation_gain_m: 0 },
      { order: 2, discipline: 'run' as const, distance_km: 2.567, elevation_gain_m: 0 },
    ]
    expect(computeTotals(legs).total_distance_km).toBe(3.8)
  })

  it('returns 0/0 for empty legs', () => {
    expect(computeTotals([])).toEqual({
      total_distance_km: 0,
      total_elevation_gain_m: 0,
    })
  })
})

describe('perfSchema', () => {
  it('accepts an empty payload (tous optional)', () => {
    expect(perfSchema.safeParse({}).success).toBe(true)
  })

  it('rejects FTP=49', () => {
    expect(perfSchema.safeParse({ ftp_watts: 49 }).success).toBe(false)
  })

  it('rejects FTP=601', () => {
    expect(perfSchema.safeParse({ ftp_watts: 601 }).success).toBe(false)
  })

  it('rejects vma below 5', () => {
    expect(perfSchema.safeParse({ vma_kmh: 4.99 }).success).toBe(false)
  })

  it('rejects vma above 30', () => {
    expect(perfSchema.safeParse({ vma_kmh: 30.01 }).success).toBe(false)
  })

  it('rejects fc_max_bpm out of [100,230]', () => {
    expect(perfSchema.safeParse({ fc_max_bpm: 99 }).success).toBe(false)
    expect(perfSchema.safeParse({ fc_max_bpm: 231 }).success).toBe(false)
  })

  it('accepts css_per_100m_s within [40,300]', () => {
    expect(perfSchema.safeParse({ css_per_100m_s: 95 }).success).toBe(true)
  })

  it('rejects css_per_100m_s below 40', () => {
    expect(perfSchema.safeParse({ css_per_100m_s: 39 }).success).toBe(false)
  })

  it('rejects css_per_100m_s above 300', () => {
    expect(perfSchema.safeParse({ css_per_100m_s: 301 }).success).toBe(false)
  })
})

describe('dispoSchema', () => {
  it('accepts an empty payload (tous optional → defaults appliqués ailleurs)', () => {
    expect(dispoSchema.safeParse({}).success).toBe(true)
  })

  it('rejects sports_strengths score out of [1,5]', () => {
    expect(
      dispoSchema.safeParse({
        sports_strengths: { swim: 0, bike: 3, run: 3 },
      }).success
    ).toBe(false)
  })

  it('rejects hours_per_week=0', () => {
    expect(dispoSchema.safeParse({ hours_per_week: 0 }).success).toBe(false)
  })

  it('rejects available_days containing unknown day', () => {
    expect(dispoSchema.safeParse({ available_days: ['mon', 'funday'] }).success).toBe(false)
  })
})

describe('DISPO_DEFAULTS', () => {
  it('validates against the schema', () => {
    expect(dispoSchema.safeParse(DISPO_DEFAULTS).success).toBe(true)
  })
})
