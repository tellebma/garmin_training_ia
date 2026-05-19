import { describe, expect, it } from 'vitest'
import {
  personSchema,
  raceSchema,
  perfSchema,
  dispoSchema,
  DISPO_DEFAULTS,
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
  const valid = { race_date: future, race_distance: 'olympique' as const }

  it('accepts a valid minimal payload', () => {
    expect(raceSchema.safeParse(valid).success).toBe(true)
  })

  it('rejects past race_date', () => {
    expect(raceSchema.safeParse({ ...valid, race_date: '2000-01-01' }).success).toBe(false)
  })

  it('rejects unknown distance', () => {
    expect(raceSchema.safeParse({ ...valid, race_distance: 'mega' }).success).toBe(false)
  })

  it('rejects target_time below 600s', () => {
    expect(raceSchema.safeParse({ ...valid, target_time_seconds: 599 }).success).toBe(false)
  })

  it('rejects target_time above 86400s', () => {
    expect(raceSchema.safeParse({ ...valid, target_time_seconds: 90000 }).success).toBe(false)
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
