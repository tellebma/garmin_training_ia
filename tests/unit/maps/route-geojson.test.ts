import { describe, expect, it } from 'vitest'
import { buildRouteGeoJson, routeBounds } from '@/lib/maps/route-geojson'

describe('buildRouteGeoJson', () => {
  it('builds a LineString from valid points', () => {
    const feature = buildRouteGeoJson([
      { latitude: 45.1, longitude: 4.1 },
      { latitude: 45.2, longitude: 4.2 },
    ])
    expect(feature).not.toBeNull()
    expect(feature?.geometry.coordinates).toEqual([
      [4.1, 45.1],
      [4.2, 45.2],
    ])
  })

  it('skips points without coordinates', () => {
    const feature = buildRouteGeoJson([
      { latitude: 45.1, longitude: 4.1 },
      { latitude: null, longitude: 4.2 },
      { latitude: 45.3, longitude: 4.3 },
    ])
    expect(feature?.geometry.coordinates).toEqual([
      [4.1, 45.1],
      [4.3, 45.3],
    ])
  })

  it('returns null with fewer than two valid points', () => {
    expect(buildRouteGeoJson([{ latitude: 45.1, longitude: 4.1 }])).toBeNull()
    expect(buildRouteGeoJson([])).toBeNull()
  })
})

describe('routeBounds', () => {
  it('computes the bounding box', () => {
    expect(
      routeBounds([
        [4.1, 45.1],
        [4.3, 45.0],
        [4.2, 45.4],
      ])
    ).toEqual([
      [4.1, 45.0],
      [4.3, 45.4],
    ])
  })

  it('returns null when empty', () => {
    expect(routeBounds([])).toBeNull()
  })
})
