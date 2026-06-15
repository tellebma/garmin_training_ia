import { describe, expect, it } from 'vitest'
import {
  buildActivityCoachAnalysis,
  summarizeSimilarActivities,
  type ActivityDetail,
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
