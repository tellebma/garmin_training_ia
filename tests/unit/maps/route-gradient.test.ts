import { describe, expect, it } from 'vitest'
import { availableMetrics, buildMetricGradient, metricColor } from '@/lib/maps/route-gradient'
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

describe('metricColor', () => {
  it('returns distinct hsl colors across the range and clamps', () => {
    expect(metricColor(0)).toMatch(/^hsl\(/)
    expect(metricColor(1)).toMatch(/^hsl\(/)
    expect(metricColor(0)).not.toBe(metricColor(1))
    expect(metricColor(-5)).toBe(metricColor(0))
    expect(metricColor(5)).toBe(metricColor(1))
  })
})

describe('availableMetrics', () => {
  it('lists only metrics with at least two values on GPS points', () => {
    const samples = [
      sample({ latitude: 45.0, longitude: 4.0, heart_rate_bpm: 120, speed_m_s: 3 }),
      sample({ latitude: 45.1, longitude: 4.1, heart_rate_bpm: 140 }),
    ]
    expect(availableMetrics(samples)).toEqual(['hr'])
  })
})

describe('buildMetricGradient', () => {
  it('builds an interpolate expression with monotonic stops in [0,1]', () => {
    const samples = [
      sample({ latitude: 45.0, longitude: 4.0, heart_rate_bpm: 120 }),
      sample({ latitude: 45.1, longitude: 4.1, heart_rate_bpm: 150 }),
      sample({ latitude: 45.2, longitude: 4.2, heart_rate_bpm: 180 }),
    ]
    const expr = buildMetricGradient(samples, 'hr')
    expect(expr).not.toBeNull()
    expect(expr?.slice(0, 3)).toEqual(['interpolate', ['linear'], ['line-progress']])
    const stops = (expr ?? []).slice(3).filter((_, i) => i % 2 === 0) as number[]
    expect(stops[0]).toBe(0)
    expect(stops[stops.length - 1]).toBe(1)
    for (let i = 1; i < stops.length; i++) {
      const prev = stops[i - 1] ?? -Infinity
      expect(stops[i]).toBeGreaterThan(prev)
    }
  })

  it('forward/back-fills missing metric values without dropping geometry', () => {
    const samples = [
      sample({ latitude: 45.0, longitude: 4.0, heart_rate_bpm: null }),
      sample({ latitude: 45.1, longitude: 4.1, heart_rate_bpm: 150 }),
      sample({ latitude: 45.2, longitude: 4.2, heart_rate_bpm: null }),
    ]
    const expr = buildMetricGradient(samples, 'hr')
    expect(expr).not.toBeNull()
  })

  it('returns null when fewer than two GPS points', () => {
    expect(
      buildMetricGradient([sample({ latitude: 45.0, longitude: 4.0, heart_rate_bpm: 120 })], 'hr')
    ).toBeNull()
  })

  it('returns null when no metric value exists', () => {
    const samples = [
      sample({ latitude: 45.0, longitude: 4.0 }),
      sample({ latitude: 45.1, longitude: 4.1 }),
    ]
    expect(buildMetricGradient(samples, 'hr')).toBeNull()
  })
})
