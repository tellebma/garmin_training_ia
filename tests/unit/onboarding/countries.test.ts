import { describe, it, expect } from 'vitest'
import { COMMON_COUNTRIES } from '@/lib/onboarding/countries'

describe('COMMON_COUNTRIES', () => {
  it('contains France first (default audience)', () => {
    expect(COMMON_COUNTRIES[0]).toBe('France')
  })

  it('contains the main French-speaking countries', () => {
    expect(COMMON_COUNTRIES).toContain('Belgique')
    expect(COMMON_COUNTRIES).toContain('Suisse')
    expect(COMMON_COUNTRIES).toContain('Canada')
  })

  it('has no duplicates', () => {
    const set = new Set(COMMON_COUNTRIES)
    expect(set.size).toBe(COMMON_COUNTRIES.length)
  })

  it('all entries are non-empty strings', () => {
    for (const c of COMMON_COUNTRIES) {
      expect(typeof c).toBe('string')
      expect(c.length).toBeGreaterThan(0)
    }
  })
})
