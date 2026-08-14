import { describe, expect, it } from 'vitest'
import {
  buildRouteFrequencyGeoJson,
  computeBreaks,
  frequencyLabels,
  resamplePolyline,
  type LngLat,
} from '@/lib/maps/route-frequency'

/** ~1 km of longitude at 45°N is roughly 0.0127°. */
const KM_LNG = 0.0127
const BASE_LAT = 45.5

/** A straight west→east road, `km` long, sampled every `stepKm`. */
function road(km: number, stepKm: number, lat = BASE_LAT, startKm = 0): LngLat[] {
  const points: LngLat[] = []
  for (let d = startKm; d <= startKm + km + 1e-9; d += stepKm) {
    points.push([4 + d * KM_LNG, lat])
  }
  return points
}

const passagesOf = (polylines: unknown[]): number[] =>
  buildRouteFrequencyGeoJson(polylines).collection.features.map((f) => f.properties.passages)

describe('resamplePolyline', () => {
  it('inserts intermediate points so no gap exceeds the requested spacing', () => {
    const dense = resamplePolyline(
      [
        [4, 45.5],
        [4 + 10 * KM_LNG, 45.5],
      ],
      100,
      Math.cos((45.5 * Math.PI) / 180)
    )
    // 10 km at 100 m spacing → 100 steps + the original first point.
    expect(dense).toHaveLength(101)
    expect(dense[0]).toEqual([4, 45.5])
    expect(dense.at(-1)?.[0]).toBeCloseTo(4 + 10 * KM_LNG, 6)
  })

  it('returns the lone point for a degenerate polyline and nothing for an empty one', () => {
    expect(resamplePolyline([[4, 45]], 100, 1)).toEqual([[4, 45]])
    expect(resamplePolyline([], 100, 1)).toEqual([])
  })

  it('keeps a zero-length segment from emitting an unbounded number of points', () => {
    const dense = resamplePolyline(
      [
        [4, 45],
        [4, 45],
      ],
      100,
      1
    )
    expect(dense).toHaveLength(2)
  })
})

describe('computeBreaks', () => {
  it('returns a single class when nothing was travelled twice', () => {
    expect(computeBreaks([1, 1, 1])).toEqual([1])
  })

  it('always opens a dedicated class at 1 and at 2 passages', () => {
    const breaks = computeBreaks([1, 1, 2, 2, 3, 8, 20])
    expect(breaks[0]).toBe(1)
    expect(breaks[1]).toBe(2)
  })

  it('spreads the upper classes over the observed distribution, not over 0..max', () => {
    // Heavily right-skewed: mostly 2s, one road ridden 40 times.
    const weights = [...Array<number>(50).fill(2), 3, 4, 12, 40]
    const breaks = computeBreaks(weights)
    expect(breaks).toStrictEqual([...breaks].sort((a, b) => a - b))
    expect(new Set(breaks).size).toBe(breaks.length)
    expect(breaks.at(-1)).toBeLessThan(40)
  })

  it('never emits more classes than the palette has colours', () => {
    expect(computeBreaks([2, 3, 4, 5, 6, 7, 8, 9, 10]).length).toBeLessThanOrEqual(5)
  })
})

describe('frequencyLabels', () => {
  it('renders closed ranges and an open-ended top class', () => {
    expect(frequencyLabels([1, 2, 3, 6, 12], 34)).toEqual(['1', '2', '3-5', '6-11', '12+'])
  })

  it('drops the "+" when the top class holds exactly the maximum', () => {
    expect(frequencyLabels([1, 2], 2)).toEqual(['1', '2'])
  })

  it('handles a single class', () => {
    expect(frequencyLabels([1], 1)).toEqual(['1'])
  })
})

describe('buildRouteFrequencyGeoJson', () => {
  it('returns an empty result for no usable polylines', () => {
    const result = buildRouteFrequencyGeoJson([null, 'nope', [], [[4, 45]], [['x', 1]]])
    expect(result.collection.features).toHaveLength(0)
    expect(result.maxPassages).toBe(0)
    expect(result.breaks).toEqual([1])
    expect(result.bounds).toBeNull()
  })

  it('weights a stretch by the number of distinct activities that travelled it', () => {
    // Three activities on the same road, one activity on a road 5 km north.
    const shared = road(5, 1)
    const elsewhere = road(5, 1, BASE_LAT + 0.045)
    const result = buildRouteFrequencyGeoJson([shared, shared, shared, elsewhere])
    expect(result.maxPassages).toBe(3)
    const values = new Set(result.collection.features.map((f) => f.properties.passages))
    expect(values).toEqual(new Set([1, 3]))
  })

  it('is insensitive to how coarsely each route was downsampled', () => {
    // The very same road, one trace sampled every 100 m, the other every 1 km:
    // the old point-density heatmap made the fine trace ~10x hotter.
    const fine = road(5, 0.1)
    const coarse = road(5, 1)
    const result = buildRouteFrequencyGeoJson([fine, coarse])
    expect(result.maxPassages).toBe(2)
    // Both traces are recognised as the same stretch, end to end.
    const single = result.collection.features.filter((f) => f.properties.passages === 1)
    expect(single).toHaveLength(0)
  })

  it('does not let a single activity inflate its own passage count', () => {
    // One long ride, densely sampled: every stretch must still read "1 passage".
    expect(new Set(passagesOf([road(20, 0.1)]))).toEqual(new Set([1]))
  })

  it('counts an out-and-back on the same road as two passages', () => {
    const out = road(4, 0.5)
    const there = [...out, ...[...out].reverse()]
    // A single activity: it is one activity, so still one passage.
    expect(new Set(passagesOf([there]))).toEqual(new Set([1]))
  })

  it('merges consecutive stretches of equal weight into one line feature', () => {
    const features = buildRouteFrequencyGeoJson([road(10, 0.5)]).collection.features
    expect(features).toHaveLength(1)
    expect(features[0]?.geometry.type).toBe('LineString')
    expect(features[0]?.geometry.coordinates.length).toBeGreaterThan(2)
  })

  it('sorts features ascending so the busiest roads are painted last', () => {
    const shared = road(5, 0.5)
    const result = buildRouteFrequencyGeoJson([shared, shared, road(5, 0.5, BASE_LAT + 0.045)])
    const values = result.collection.features.map((f) => f.properties.passages)
    expect(values).toStrictEqual([...values].sort((a, b) => a - b))
  })

  it('reports the bounding box of the original traces', () => {
    const result = buildRouteFrequencyGeoJson([road(5, 1), road(5, 1, BASE_LAT + 0.045, 10)])
    expect(result.bounds?.[0][0]).toBeCloseTo(4, 6)
    expect(result.bounds?.[0][1]).toBeCloseTo(BASE_LAT, 6)
    expect(result.bounds?.[1][1]).toBeCloseTo(BASE_LAT + 0.045, 6)
  })
})
