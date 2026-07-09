import { describe, expect, it } from 'vitest'
import { computeColsSummary, haversineKm } from '@/lib/dashboard/cols'
import type { ColCrossingRowDto, ColDto } from '@/lib/dashboard/cols'

const HOME_LAT = 45.0
const HOME_LON = 6.0

function mkCol(overrides: Partial<ColDto>): ColDto {
  return {
    id: 'col-1',
    name: 'Col du Truc',
    latitude: 45.05,
    longitude: 6.05,
    elevation_m: 1850,
    ...overrides,
  }
}

describe('haversineKm', () => {
  it('returns 0 for identical points', () => {
    expect(haversineKm(45.0, 6.0, 45.0, 6.0)).toBe(0)
  })

  it('computes the known Paris-Lyon distance (~391km)', () => {
    const km = haversineKm(48.8566, 2.3522, 45.764, 4.8357)
    expect(km).toBeGreaterThan(385)
    expect(km).toBeLessThan(400)
  })
})

describe('computeColsSummary', () => {
  it('filters out cols beyond the radius', () => {
    const cols: ColDto[] = [
      mkCol({ id: 'near', latitude: 45.05, longitude: 6.05 }),
      mkCol({ id: 'far', latitude: 50.0, longitude: 2.0 }),
    ]
    const out = computeColsSummary({ homeLat: HOME_LAT, homeLon: HOME_LON, cols, crossings: [] })
    expect(out.map((c) => c.id)).toEqual(['near'])
  })

  it('counts crossings per col and keeps 0-count cols', () => {
    const cols: ColDto[] = [
      mkCol({ id: 'col-a', latitude: 45.01, longitude: 6.01 }),
      mkCol({ id: 'col-b', latitude: 45.02, longitude: 6.02 }),
    ]
    const crossings: ColCrossingRowDto[] = [
      { col_id: 'col-a', crossed_at: '2026-06-01T08:00:00Z' },
      { col_id: 'col-a', crossed_at: '2026-06-15T08:00:00Z' },
    ]
    const out = computeColsSummary({ homeLat: HOME_LAT, homeLon: HOME_LON, cols, crossings })
    const colA = out.find((c) => c.id === 'col-a')
    const colB = out.find((c) => c.id === 'col-b')
    expect(colA?.crossingsCount).toBe(2)
    expect(colA?.lastCrossedAt).toBe('2026-06-15T08:00:00Z')
    expect(colB?.crossingsCount).toBe(0)
    expect(colB?.lastCrossedAt).toBeNull()
  })

  it('sorts by crossings count desc, then distance asc', () => {
    const cols: ColDto[] = [
      mkCol({ id: 'far-climbed', latitude: 45.04, longitude: 6.04 }),
      mkCol({ id: 'near-unclimbed', latitude: 45.01, longitude: 6.01 }),
      mkCol({ id: 'far-unclimbed', latitude: 45.03, longitude: 6.03 }),
    ]
    const crossings: ColCrossingRowDto[] = [
      { col_id: 'far-climbed', crossed_at: '2026-06-01T08:00:00Z' },
    ]
    const out = computeColsSummary({ homeLat: HOME_LAT, homeLon: HOME_LON, cols, crossings })
    expect(out.map((c) => c.id)).toEqual(['far-climbed', 'near-unclimbed', 'far-unclimbed'])
  })

  it('returns an empty array when there are no cols in range', () => {
    const out = computeColsSummary({
      homeLat: HOME_LAT,
      homeLon: HOME_LON,
      cols: [],
      crossings: [],
    })
    expect(out).toEqual([])
  })
})
