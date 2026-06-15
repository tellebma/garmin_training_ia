import { describe, expect, it } from 'vitest'
import {
  buildActivityCoachAnalysis,
  summarizeActivitySamples,
  summarizeSimilarActivities,
  type ActivityDetail,
  type ActivitySample,
} from '@/lib/coach/activity-analysis'
import type { PlannedSession } from '@/lib/dashboard/types'

const baseActivity: ActivityDetail = {
  id: 'a1',
  garmin_activity_id: 123,
  start_time: '2026-06-14T08:00:00Z',
  sport: 'run',
  duration_s: 3600,
  distance_m: 10_000,
  elevation_gain_m: 120,
  tss: 65,
  hr_avg: 148,
  hr_max: 174,
  power_avg: null,
  power_max: null,
  pace_avg_s_per_km: 360,
  calories: 720,
}

const planned: PlannedSession = {
  id: 'p1',
  date: '2026-06-14',
  sport: 'run',
  session_type: 'endurance',
  target_duration_s: 3600,
  target_tss: 60,
  target_elevation_gain_m: 100,
  phase: 'base',
  week_offset: 1,
  notes: null,
}

describe('summarizeSimilarActivities', () => {
  it('computes averages over available numeric metrics', () => {
    const summary = summarizeSimilarActivities([
      baseActivity,
      { ...baseActivity, id: 'a2', duration_s: 5400, tss: 95, hr_avg: null },
    ])

    expect(summary.count).toBe(2)
    expect(summary.avg_duration_s).toBe(4500)
    expect(summary.avg_tss).toBe(80)
    expect(summary.avg_hr_avg).toBe(148)
  })
})

describe('buildActivityCoachAnalysis', () => {
  it('flags a session that is much more intense than planned', () => {
    const analysis = buildActivityCoachAnalysis({
      activity: { ...baseActivity, tss: 100 },
      plannedSession: planned,
      similar: summarizeSimilarActivities([baseActivity]),
    })

    expect(analysis.tone).toBe('risk')
    expect(analysis.title).toBe('Séance plus intense que prévu')
    expect(analysis.insights).toContain('La charge réalisée dépasse nettement la cible du plan.')
    expect(analysis.recommendations.join(' ')).toMatch(/24 à 48 heures/)
  })

  it('recommends slowing down climbs when elevation and heart rate are high', () => {
    const analysis = buildActivityCoachAnalysis({
      activity: { ...baseActivity, elevation_gain_m: 620, hr_avg: 166 },
      plannedSession: planned,
      similar: summarizeSimilarActivities([baseActivity]),
    })

    expect(analysis.tone).toBe('watch')
    expect(analysis.recommendations.join(' ')).toMatch(/montées/)
    expect(analysis.recommendations.join(' ')).toMatch(/161 bpm/)
  })

  it('keeps a positive tone for a well executed activity', () => {
    const analysis = buildActivityCoachAnalysis({
      activity: baseActivity,
      plannedSession: planned,
      similar: summarizeSimilarActivities([baseActivity]),
    })

    expect(analysis.tone).toBe('positive')
    expect(analysis.title).toBe('Bonne activité')
    expect(analysis.insights[0]).toMatch(/Exécution cohérente/)
  })
})

describe('summarizeActivitySamples', () => {
  const samples: ActivitySample[] = [
    {
      sample_index: 0,
      sample_time: null,
      elapsed_s: 0,
      distance_m: 0,
      elevation_m: 100,
      heart_rate_bpm: 120,
      power_w: null,
      cadence_rpm: null,
      speed_m_s: 2.5,
    },
    {
      sample_index: 1,
      sample_time: null,
      elapsed_s: 60,
      distance_m: 200,
      elevation_m: 112,
      heart_rate_bpm: 166,
      power_w: null,
      cadence_rpm: null,
      speed_m_s: 2.4,
    },
    {
      sample_index: 2,
      sample_time: null,
      elapsed_s: 120,
      distance_m: 500,
      elevation_m: 113,
      heart_rate_bpm: 170,
      power_w: null,
      cadence_rpm: null,
      speed_m_s: 3.1,
    },
    {
      sample_index: 3,
      sample_time: null,
      elapsed_s: 180,
      distance_m: 700,
      elevation_m: 104,
      heart_rate_bpm: 150,
      power_w: null,
      cadence_rpm: null,
      speed_m_s: 3.4,
    },
  ]

  it('summarizes heart-rate zones from samples', () => {
    const summary = summarizeActivitySamples(samples, 190)

    expect(summary.hrZones.find((z) => z.zone === 'Z3')?.percent).toBe(25)
    expect(summary.hrZones.find((z) => z.zone === 'Z4')?.percent).toBe(50)
    expect(summary.hrZones.find((z) => z.zone === 'Z5')?.percent).toBe(0)
  })

  it('summarizes climb flat and descent terrain', () => {
    const summary = summarizeActivitySamples(samples, 190)

    const climb = summary.terrain.find((segment) => segment.terrain === 'Montée')
    const flat = summary.terrain.find((segment) => segment.terrain === 'Plat')
    const descent = summary.terrain.find((segment) => segment.terrain === 'Descente')

    expect(climb?.distance_m).toBe(200)
    expect(climb?.avg_grade_pct).toBe(6)
    expect(flat?.distance_m).toBe(300)
    expect(descent?.distance_m).toBe(200)
    expect(summary.recommendations.join(' ')).toMatch(/ralentis tôt/)
  })

  it('detects cardio drift when heart rate rises without speed gain', () => {
    const driftSamples: ActivitySample[] = [130, 132, 134, 136, 145, 147, 149, 151].map(
      (heartRate, index) => ({
        sample_index: index,
        sample_time: null,
        elapsed_s: index * 60,
        distance_m: index * 180,
        elevation_m: 100,
        heart_rate_bpm: heartRate,
        power_w: null,
        cadence_rpm: null,
        speed_m_s: 3,
      })
    )

    const summary = summarizeActivitySamples(driftSamples, 190)

    expect(summary.cardioDrift.signal).toBe('risk')
    expect(summary.cardioDrift.drift_bpm).toBe(15)
    expect(summary.cardioDrift.speed_change_pct).toBe(0)
    expect(summary.recommendations.join(' ')).toMatch(/pars plus bas/)
  })

  it('detects irregular pacing by terrain segment', () => {
    const irregularSamples: ActivitySample[] = [2, 5, 2, 5, 2].map((speed, index) => ({
      sample_index: index,
      sample_time: null,
      elapsed_s: index * 60,
      distance_m: index * 200,
      elevation_m: 100 + index,
      heart_rate_bpm: 130,
      power_w: null,
      cadence_rpm: null,
      speed_m_s: speed,
    }))

    const summary = summarizeActivitySamples(irregularSamples, 190)
    const flat = summary.terrain.find((segment) => segment.terrain === 'Plat')

    expect(flat?.speed_variability_pct).toBeGreaterThan(35)
    expect(summary.insights.join(' ')).toMatch(/Pacing irrégulier/)
    expect(summary.recommendations.join(' ')).toMatch(/régularité/)
  })
})
