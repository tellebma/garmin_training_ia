import { describe, expect, it } from 'vitest'
import { mapRecoveryRow } from '@/lib/dashboard/recovery'

const sampleMetric = {
  baseline: 50,
  recent: 70,
  trend: 'improving',
  confidence: 'high',
  freshness: 'fresh',
  days_covered: 28,
  last_date: '2026-06-27',
}

describe('mapRecoveryRow', () => {
  it('returns null for a missing row', () => {
    expect(mapRecoveryRow(null)).toBeNull()
    expect(mapRecoveryRow(undefined)).toBeNull()
  })

  it('maps a full row into typed baselines', () => {
    const row = {
      computed_at: '2026-06-27T05:00:00Z',
      hrv: sampleMetric,
      resting_hr: { ...sampleMetric, trend: 'declining' },
      sleep: { ...sampleMetric, duration_baseline_s: 27000, score_baseline: 80 },
      stress: sampleMetric,
      body_battery: sampleMetric,
    }
    const result = mapRecoveryRow(row)
    expect(result).not.toBeNull()
    expect(result?.hrv.trend).toBe('improving')
    expect(result?.restingHr.trend).toBe('declining')
    expect(result?.sleep.durationBaselineS).toBe(27000)
  })

  it('fills defaults for sparse metric objects', () => {
    const result = mapRecoveryRow({ hrv: {}, sleep: {} })
    expect(result).not.toBeNull()
    expect(result?.hrv.baseline).toBeNull()
    expect(result?.hrv.trend).toBe('no_data')
    expect(result?.hrv.confidence).toBe('no_data')
    expect(result?.hrv.freshness).toBe('no_data')
    expect(result?.hrv.daysCovered).toBe(0)
    expect(result?.hrv.lastDate).toBeNull()
    expect(result?.sleep.durationBaselineS).toBeNull()
    expect(result?.sleep.scoreBaseline).toBeNull()
  })

  it('handles a row with all metrics absent', () => {
    const result = mapRecoveryRow({})
    expect(result).not.toBeNull()
    expect(result?.computedAt).toBeNull()
    expect(result?.restingHr.trend).toBe('no_data')
    expect(result?.bodyBattery.confidence).toBe('no_data')
  })
})
