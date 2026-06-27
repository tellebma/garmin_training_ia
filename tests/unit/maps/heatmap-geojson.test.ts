import { describe, expect, it } from 'vitest'
import { buildHeatmapGeoJson } from '@/lib/maps/heatmap-geojson'

describe('buildHeatmapGeoJson', () => {
  it('flattens all valid polyline points into Point features', () => {
    const fc = buildHeatmapGeoJson([
      [
        [4.0, 45.0],
        [4.1, 45.1],
      ],
      [[5.0, 46.0]],
    ])
    expect(fc.type).toBe('FeatureCollection')
    expect(fc.features).toHaveLength(3)
    expect(fc.features[0]?.geometry).toEqual({ type: 'Point', coordinates: [4.0, 45.0] })
  })

  it('ignores null, empty sentinel, and malformed entries', () => {
    const fc = buildHeatmapGeoJson([
      null,
      [],
      'nope',
      [
        [4.0, 45.0],
        ['x', 1],
      ],
    ])
    expect(fc.features).toHaveLength(1)
  })
})
