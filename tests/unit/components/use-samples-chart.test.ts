import { describe, expect, it } from 'vitest'
import {
  hasDistance,
  availableMetrics,
  buildChartData,
} from '@/app/(app)/_components/charts/use-samples-chart'
import type { ActivitySample } from '@/lib/coach/activity-analysis'

function sample(partial: Partial<ActivitySample>): ActivitySample {
  return {
    sample_index: 0,
    sample_time: null,
    elapsed_s: null,
    distance_m: null,
    elevation_m: null,
    heart_rate_bpm: null,
    power_w: null,
    cadence_rpm: null,
    speed_m_s: null,
    latitude: null,
    longitude: null,
    ...partial,
  }
}

describe('hasDistance', () => {
  it('is true when at least one sample has distance', () => {
    expect(hasDistance([sample({}), sample({ distance_m: 12 })])).toBe(true)
  })
  it('is false when no sample has distance', () => {
    expect(hasDistance([sample({}), sample({})])).toBe(false)
  })
})

describe('availableMetrics', () => {
  it('includes only present metrics in fixed order', () => {
    const data = [sample({ heart_rate_bpm: 120, power_w: 200 })]
    const keys = availableMetrics(data, 'bike').map((m) => m.key)
    expect(keys).toEqual(['heart_rate_bpm', 'power_w'])
  })
  it('labels the speed metric per sport', () => {
    const data = [sample({ speed_m_s: 3 })]
    const runMetrics = availableMetrics(data, 'run')
    expect(runMetrics).toContainEqual(
      expect.objectContaining({
        key: 'speed',
        unit: 'min/km',
        inverted: true,
      })
    )
    const bikeMetrics = availableMetrics(data, 'bike')
    expect(bikeMetrics).toContainEqual(
      expect.objectContaining({
        key: 'speed',
        unit: 'km/h',
        inverted: false,
      })
    )
  })
})

describe('buildChartData', () => {
  it('uses elapsed minutes for time basis', () => {
    const data = [sample({ elapsed_s: 120, heart_rate_bpm: 130 })]
    const points = buildChartData(data, 'bike', 'time')
    expect(points).toHaveLength(1)
    expect(points[0]).toMatchObject({ x: 2 })
  })
  it('uses km for distance basis and converts speed per sport', () => {
    const data = [sample({ distance_m: 5000, speed_m_s: 10 })]
    const points = buildChartData(data, 'bike', 'distance')
    expect(points).toHaveLength(1)
    expect(points[0]).toMatchObject({
      x: 5,
      speed: expect.closeTo(36, 5),
    })
  })
})
