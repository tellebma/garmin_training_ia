import { describe, expect, it } from 'vitest'
import { computeColsSummary, haversineKm, toActivityColCrossings } from '@/lib/dashboard/cols'
import type { ColCrossingRowDto, ColDto, ActivityColCrossingDto } from '@/lib/dashboard/cols'

const HOME_LAT = 45.0
const HOME_LON = 6.0

function mkCol(overrides: Partial<ColDto>): ColDto {
  return {
    id: 'col-1',
    name: 'Col du Truc',
    latitude: 45.05,
    longitude: 6.05,
    elevation_m: 1850,
    type: 'col',
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
  it('filters out unclimbed cols beyond the radius', () => {
    const cols: ColDto[] = [
      mkCol({ id: 'near', latitude: 45.05, longitude: 6.05 }),
      mkCol({ id: 'far', latitude: 50.0, longitude: 2.0 }),
    ]
    const out = computeColsSummary({ homeLat: HOME_LAT, homeLon: HOME_LON, cols, crossings: [] })
    expect(out.cols.map((c) => c.id)).toEqual(['near'])
  })

  it('keeps climbed cols regardless of distance (régression col du Chaussy)', () => {
    // Un col gravi pendant un déplacement (bien au-delà des 50 km du domicile)
    // doit apparaître dans les stats ; un col lointain jamais gravi reste exclu.
    const cols: ColDto[] = [
      mkCol({ id: 'chaussy', name: 'Col du Chaussy', latitude: 50.0, longitude: 2.0 }),
      mkCol({ id: 'far-unclimbed', latitude: 50.1, longitude: 2.1 }),
      mkCol({ id: 'near', latitude: 45.05, longitude: 6.05 }),
    ]
    const crossings: ColCrossingRowDto[] = [
      { col_id: 'chaussy', crossed_at: '2026-07-25T08:23:31Z' },
    ]
    const out = computeColsSummary({ homeLat: HOME_LAT, homeLon: HOME_LON, cols, crossings })
    expect(out.cols.map((c) => c.id)).toEqual(['chaussy', 'near'])
    expect(out.cols[0]?.crossingsCount).toBe(1)
  })

  it('caps each group at 30 results, keeping the best-ranked ones', () => {
    const cols: ColDto[] = Array.from({ length: 40 }, (_, i) =>
      mkCol({ id: `col-${String(i)}`, latitude: 45.001 + i * 0.001, longitude: 6.0 })
    )
    const crossings: ColCrossingRowDto[] = [
      // Le col le plus lointain du lot est gravi : il doit rester malgré le cap.
      { col_id: 'col-39', crossed_at: '2026-07-01T08:00:00Z' },
    ]
    const out = computeColsSummary({ homeLat: HOME_LAT, homeLon: HOME_LON, cols, crossings })
    expect(out.cols).toHaveLength(30)
    expect(out.cols[0]?.id).toBe('col-39')
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
    const colA = out.cols.find((c) => c.id === 'col-a')
    const colB = out.cols.find((c) => c.id === 'col-b')
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
    expect(out.cols.map((c) => c.id)).toEqual(['far-climbed', 'near-unclimbed', 'far-unclimbed'])
  })

  it('returns empty groups when there are no cols in range', () => {
    const out = computeColsSummary({
      homeLat: HOME_LAT,
      homeLon: HOME_LON,
      cols: [],
      crossings: [],
    })
    expect(out).toEqual({ cols: [], peaks: [] })
  })

  it('groups cols and peaks into separate, independently sorted lists', () => {
    const cols: ColDto[] = [
      mkCol({ id: 'col-a', latitude: 45.01, longitude: 6.01, type: 'col' }),
      mkCol({
        id: 'peak-a',
        latitude: 45.02,
        longitude: 6.02,
        type: 'peak',
        name: 'Crêt du Machin',
      }),
      mkCol({
        id: 'peak-b',
        latitude: 45.03,
        longitude: 6.03,
        type: 'peak',
        name: 'Crêt du Bidule',
      }),
    ]
    const crossings: ColCrossingRowDto[] = [
      { col_id: 'peak-b', crossed_at: '2026-06-01T08:00:00Z' },
    ]
    const out = computeColsSummary({ homeLat: HOME_LAT, homeLon: HOME_LON, cols, crossings })
    expect(out.cols.map((c) => c.id)).toEqual(['col-a'])
    expect(out.peaks.map((c) => c.id)).toEqual(['peak-b', 'peak-a'])
  })
})

describe('toActivityColCrossings', () => {
  it('returns an empty array for no rows', () => {
    expect(toActivityColCrossings([])).toEqual([])
  })

  it('maps and sorts rows chronologically by crossed_at', () => {
    const rows = [
      {
        col_id: 'col-b',
        crossed_at: '2026-06-01T10:00:00Z',
        cols: { name: 'Col B', elevation_m: 1200 },
      },
      {
        col_id: 'col-a',
        crossed_at: '2026-06-01T08:00:00Z',
        cols: { name: 'Col A', elevation_m: 1800 },
      },
    ]
    const out = toActivityColCrossings(rows)
    const expected: ActivityColCrossingDto[] = [
      { colId: 'col-a', name: 'Col A', elevationM: 1800, crossedAt: '2026-06-01T08:00:00Z' },
      { colId: 'col-b', name: 'Col B', elevationM: 1200, crossedAt: '2026-06-01T10:00:00Z' },
    ]
    expect(out).toEqual(expected)
  })

  it('preserves a null elevation_m as null', () => {
    const rows = [
      {
        col_id: 'col-c',
        crossed_at: '2026-06-01T08:00:00Z',
        cols: { name: 'Col C', elevation_m: null },
      },
    ]
    expect(toActivityColCrossings(rows)[0]?.elevationM).toBeNull()
  })

  it('also accepts cols embedded as a single-element array (PostgREST inference quirk)', () => {
    const rows = [
      {
        col_id: 'col-d',
        crossed_at: '2026-06-01T08:00:00Z',
        cols: [{ name: 'Col D', elevation_m: 900 }],
      },
    ]
    expect(toActivityColCrossings(rows)).toEqual<ActivityColCrossingDto[]>([
      { colId: 'col-d', name: 'Col D', elevationM: 900, crossedAt: '2026-06-01T08:00:00Z' },
    ])
  })

  it('drops a row whose embedded cols array is empty rather than throwing', () => {
    const rows = [
      { col_id: 'col-e', crossed_at: '2026-06-01T08:00:00Z', cols: [] },
      {
        col_id: 'col-f',
        crossed_at: '2026-06-01T09:00:00Z',
        cols: { name: 'Col F', elevation_m: 1000 },
      },
    ]
    expect(toActivityColCrossings(rows).map((c) => c.colId)).toEqual(['col-f'])
  })
})
