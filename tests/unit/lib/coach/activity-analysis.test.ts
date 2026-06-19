import { describe, expect, it } from 'vitest'
import {
  buildActivityCoachAnalysis,
  buildNextSessionAdjustment,
  summarizeActivitySamples,
  summarizeSimilarActivities,
  type ActivityDetail,
  type ActivitySample,
  type SampleCoachSummary,
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

  it('protects recovery after activity on a planned rest day', () => {
    const restDay: PlannedSession = {
      ...planned,
      sport: 'rest',
      session_type: 'rest',
      target_duration_s: 0,
      target_tss: 0,
    }

    const analysis = buildActivityCoachAnalysis({
      activity: baseActivity,
      plannedSession: restDay,
      similar: summarizeSimilarActivities([baseActivity]),
    })

    expect(analysis.tone).toBe('risk')
    expect(analysis.title).toBe('Activité réalisée sur un jour de repos')
    expect(analysis.recommendations.join(' ')).toMatch(/prochaine séance très facile/)
  })

  it('flags an activity performed in a different sport than planned', () => {
    const bikePlan: PlannedSession = { ...planned, sport: 'bike' }

    const analysis = buildActivityCoachAnalysis({
      activity: baseActivity,
      plannedSession: bikePlan,
      similar: summarizeSimilarActivities([baseActivity]),
    })

    expect(analysis.tone).toBe('watch')
    expect(analysis.title).toBe('Séance différente du plan')
    expect(analysis.insights.join(' ')).toMatch(/bike prévu/)
  })

  it('warns when duration substantially exceeds the planned session', () => {
    const analysis = buildActivityCoachAnalysis({
      activity: { ...baseActivity, duration_s: 5000 },
      plannedSession: planned,
      similar: summarizeSimilarActivities([baseActivity]),
    })

    expect(analysis.tone).toBe('watch')
    expect(analysis.insights.join(' ')).toMatch(/durée réalisée/)
    expect(analysis.recommendations.join(' ')).toMatch(/jambes sont lourdes/)
  })

  it('recommends not compensating after a shortened session', () => {
    const analysis = buildActivityCoachAnalysis({
      activity: { ...baseActivity, duration_s: 1800, tss: 25 },
      plannedSession: planned,
      similar: summarizeSimilarActivities([baseActivity]),
    })

    expect(analysis.tone).toBe('watch')
    expect(analysis.title).toBe('Séance écourtée')
    expect(analysis.recommendations.join(' ')).toMatch(/Ne rattrape pas/)
  })

  it('flags unusual elevation compared with similar activities', () => {
    const noElevationTarget: PlannedSession = { ...planned, target_elevation_gain_m: null }
    const similar = summarizeSimilarActivities([
      { ...baseActivity, elevation_gain_m: 180 },
      { ...baseActivity, id: 'a2', elevation_gain_m: 220 },
    ])

    const analysis = buildActivityCoachAnalysis({
      activity: { ...baseActivity, elevation_gain_m: 400 },
      plannedSession: noElevationTarget,
      similar,
    })

    expect(analysis.tone).toBe('watch')
    expect(analysis.insights.join(' ')).toMatch(/activités similaires/)
  })

  it('handles an activity without planned session or load metrics', () => {
    const sparseActivity: ActivityDetail = {
      ...baseActivity,
      duration_s: null,
      tss: null,
      elevation_gain_m: null,
      hr_avg: null,
      power_avg: null,
    }

    const analysis = buildActivityCoachAnalysis({
      activity: sparseActivity,
      plannedSession: null,
      similar: summarizeSimilarActivities([]),
    })

    expect(analysis.tone).toBe('positive')
    expect(analysis.chartData.every((point) => point.planned === null)).toBe(true)
  })

  it.each([
    ['running', 'run'],
    ['cycling', 'bike'],
    ['swimming', 'swim'],
  ] as const)('recognizes Garmin sport alias %s as planned %s', (activitySport, plannedSport) => {
    const analysis = buildActivityCoachAnalysis({
      activity: { ...baseActivity, sport: activitySport },
      plannedSession: { ...planned, sport: plannedSport },
      similar: summarizeSimilarActivities([baseActivity]),
    })

    expect(analysis.title).not.toBe('Séance différente du plan')
  })

  it('does not add climb pacing advice for a non-endurance sport', () => {
    const analysis = buildActivityCoachAnalysis({
      activity: {
        ...baseActivity,
        sport: 'strength_training',
        elevation_gain_m: 500,
        hr_avg: 170,
      },
      plannedSession: null,
      similar: summarizeSimilarActivities([]),
    })

    expect(analysis.recommendations.join(' ')).not.toMatch(/prochaines montées/)
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

  it('returns stable defaults when no usable samples are available', () => {
    const summary = summarizeActivitySamples([], null)

    expect(summary.cardioDrift.signal).toBe('insufficient')
    expect(summary.hrZones.every((zone) => zone.percent === 0)).toBe(true)
    expect(summary.insights).toContain('Les samples ne montrent pas de dérive majeure à corriger.')
    expect(summary.recommendations).toContain(
      'Garde cette régularité et surveille surtout les sensations le lendemain.'
    )
  })

  it('detects a moderate cardio drift as watch using distance ordering', () => {
    const watchSamples: ActivitySample[] = [130, 130, 130, 136, 136, 136].map(
      (heartRate, index) => ({
        sample_index: index,
        sample_time: null,
        elapsed_s: null,
        distance_m: index * 200,
        elevation_m: null,
        heart_rate_bpm: heartRate,
        power_w: null,
        cadence_rpm: null,
        speed_m_s: 3,
      })
    )

    const summary = summarizeActivitySamples(watchSamples, 190)

    expect(summary.cardioDrift.signal).toBe('watch')
    expect(summary.cardioDrift.drift_bpm).toBe(6)
  })

  it('ignores malformed or non-progressing terrain samples', () => {
    const malformed: ActivitySample[] = [
      {
        sample_index: 0,
        sample_time: null,
        elapsed_s: null,
        distance_m: null,
        elevation_m: null,
        heart_rate_bpm: null,
        power_w: null,
        cadence_rpm: null,
        speed_m_s: null,
      },
      {
        sample_index: 1,
        sample_time: null,
        elapsed_s: null,
        distance_m: 0,
        elevation_m: 100,
        heart_rate_bpm: 120,
        power_w: null,
        cadence_rpm: null,
        speed_m_s: 0,
      },
      {
        sample_index: 2,
        sample_time: null,
        elapsed_s: null,
        distance_m: 0,
        elevation_m: 101,
        heart_rate_bpm: 121,
        power_w: null,
        cadence_rpm: null,
        speed_m_s: 0,
      },
    ]

    const summary = summarizeActivitySamples(malformed, 190)

    expect(summary.terrain.every((segment) => segment.distance_m === 0)).toBe(true)
    expect(summary.cardioDrift.signal).toBe('insufficient')
  })
})

describe('buildNextSessionAdjustment', () => {
  const nextHardSession: PlannedSession = {
    ...planned,
    id: 'next-hard',
    date: '2026-06-15',
    session_type: 'intervals',
    target_duration_s: 3600,
    target_tss: 75,
  }

  const nextEasySession: PlannedSession = {
    ...planned,
    id: 'next-easy',
    date: '2026-06-15',
    session_type: 'recovery',
    target_duration_s: 2400,
    target_tss: 25,
  }

  const stableSummary: SampleCoachSummary = {
    hrZones: [
      { zone: 'Z1', label: 'Récupération', samples: 10, percent: 20 },
      { zone: 'Z2', label: 'Endurance', samples: 40, percent: 80 },
      { zone: 'Z3', label: 'Tempo', samples: 0, percent: 0 },
      { zone: 'Z4', label: 'Seuil', samples: 0, percent: 0 },
      { zone: 'Z5', label: 'Très intense', samples: 0, percent: 0 },
    ],
    terrain: [],
    cardioDrift: {
      signal: 'stable',
      first_half_avg_hr_bpm: 135,
      second_half_avg_hr_bpm: 136,
      drift_bpm: 1,
      drift_pct: 0.7,
      first_half_avg_speed_kmh: 10,
      second_half_avg_speed_kmh: 10,
      speed_change_pct: 0,
    },
    insights: [],
    recommendations: [],
  }

  it('keeps the plan when detailed activity data is unavailable', () => {
    const adjustment = buildNextSessionAdjustment(null, [nextHardSession])

    expect(adjustment.action).toBe('maintain')
    expect(adjustment.targetSession?.id).toBe('next-hard')
  })

  it('protects rest when no future training session is planned', () => {
    const restSession: PlannedSession = {
      ...planned,
      id: 'next-rest',
      date: '2026-06-15',
      sport: 'rest',
      session_type: 'rest',
      target_duration_s: 0,
      target_tss: 0,
    }

    const adjustment = buildNextSessionAdjustment(stableSummary, [restSession])

    expect(adjustment.action).toBe('protect_rest')
    expect(adjustment.targetSession).toBeNull()
  })

  it('reduces the intention of a hard session after one load signal', () => {
    const oneSignalSummary: SampleCoachSummary = {
      ...stableSummary,
      hrZones: stableSummary.hrZones.map((zone) =>
        zone.zone === 'Z4' ? { ...zone, samples: 20, percent: 40 } : zone
      ),
    }

    const adjustment = buildNextSessionAdjustment(oneSignalSummary, [nextHardSession])

    expect(adjustment.action).toBe('ease')
    expect(adjustment.title).toBe('Réduire l’intention')
  })

  it('maintains the next session when detailed signals are stable', () => {
    const adjustment = buildNextSessionAdjustment(stableSummary, [nextHardSession])

    expect(adjustment.action).toBe('maintain')
    expect(adjustment.title).toBe('Suite cohérente')
  })

  it('replaces a hard next session after multiple costly signals', () => {
    const costlySamples: ActivitySample[] = [130, 132, 134, 136, 165, 168, 170, 172].map(
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
    const summary = summarizeActivitySamples(costlySamples, 190)

    const adjustment = buildNextSessionAdjustment(summary, [nextHardSession])

    expect(adjustment.action).toBe('replace_with_recovery')
    expect(adjustment.targetSession?.id).toBe('next-hard')
    expect(adjustment.recommendation).toMatch(/endurance facile|récupération active/)
  })

  it('keeps an easy next session easy after cardio drift', () => {
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

    const adjustment = buildNextSessionAdjustment(summary, [nextEasySession])

    expect(adjustment.action).toBe('ease')
    expect(adjustment.targetSession?.id).toBe('next-easy')
    expect(adjustment.recommendation).toMatch(/aisance respiratoire/)
  })
})
