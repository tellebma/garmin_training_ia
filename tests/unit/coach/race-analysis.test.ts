import { describe, expect, it } from 'vitest'
import {
  buildRaceDebrief,
  buildRaceSalute,
  buildRaceTimeline,
  compareRaces,
  expectedSharePct,
  resolveRaceElapsed,
  segmentLabel,
  summarizePreparation,
  timeBySport,
  transitionSharePct,
  type RaceActivityRow,
  type RaceGoalRow,
  type RaceSegmentRow,
} from '@/lib/coach/race-analysis'

const RACE: RaceGoalRow = {
  id: 'race-1',
  race_date: '2026-08-22',
  name: 'Triathlon de Vichy',
  location: 'Vichy',
  discipline: 'triathlon',
  legs: [
    { order: 1, discipline: 'swim', distance_km: 1.5 },
    { order: 2, discipline: 'bike', distance_km: 40 },
    { order: 3, discipline: 'run', distance_km: 10 },
  ],
  total_distance_km: 51.5,
  total_elevation_gain_m: 400,
  target_time_seconds: 9000,
  prep_start_date: '2026-06-22',
}

function segment(partial: Partial<RaceSegmentRow>): RaceSegmentRow {
  return {
    garmin_activity_id: 1,
    segment_index: 0,
    sport: 'swim',
    start_time: '2026-08-22T07:00:00Z',
    duration_s: 1800,
    distance_m: 1500,
    elevation_gain_m: 0,
    hr_avg: 150,
    pace_avg_s_per_km: 1200,
    ...partial,
  }
}

function activity(partial: Partial<RaceActivityRow>): RaceActivityRow {
  return {
    id: 'act-1',
    garmin_activity_id: 1,
    start_time: '2026-08-22T07:00:00Z',
    sport: 'swim',
    duration_s: 1800,
    distance_m: 1500,
    elevation_gain_m: 0,
    hr_avg: 150,
    pace_avg_s_per_km: 1200,
    tss: 40,
    ...partial,
  }
}

const FULL_SEGMENTS: RaceSegmentRow[] = [
  segment({ segment_index: 0, sport: 'swim', duration_s: 1800, hr_avg: 150 }),
  segment({
    segment_index: 1,
    sport: 'transition',
    duration_s: 200,
    distance_m: null,
    hr_avg: null,
  }),
  segment({ segment_index: 2, sport: 'bike', duration_s: 4200, distance_m: 40000, hr_avg: 145 }),
  segment({
    segment_index: 3,
    sport: 'transition',
    duration_s: 100,
    distance_m: null,
    hr_avg: null,
  }),
  segment({ segment_index: 4, sport: 'run', duration_s: 2700, distance_m: 10000, hr_avg: 158 }),
]

describe('buildRaceTimeline', () => {
  it('reads the multisport decomposition and names transitions T1/T2', () => {
    const timeline = buildRaceTimeline({ activities: [], segments: FULL_SEGMENTS })

    expect(timeline.map((entry) => entry.label)).toEqual([
      'Natation',
      'T1',
      'Vélo',
      'T2',
      'Course à pied',
    ])
    expect(timeline[0]?.sharePct).toBeCloseTo((1800 / 9000) * 100, 5)
  })

  it('falls back on linked activities and rebuilds transitions from the gaps', () => {
    const activities = [
      activity({ id: 'a1', sport: 'swim', start_time: '2026-08-22T07:00:00Z', duration_s: 1800 }),
      activity({
        id: 'a2',
        sport: 'bike',
        start_time: '2026-08-22T07:35:00Z',
        duration_s: 4200,
        distance_m: 40000,
      }),
    ]

    const timeline = buildRaceTimeline({ activities, segments: [] })

    expect(timeline.map((entry) => entry.sport)).toEqual(['swim', 'transition', 'bike'])
    expect(timeline[1]?.durationS).toBe(300)
  })

  it('ignores a gap too long to be a transition', () => {
    const activities = [
      activity({ id: 'a1', start_time: '2026-08-22T07:00:00Z', duration_s: 1800 }),
      activity({ id: 'a2', sport: 'run', start_time: '2026-08-22T09:00:00Z', duration_s: 2700 }),
    ]

    expect(buildRaceTimeline({ activities, segments: [] }).map((e) => e.sport)).toEqual([
      'swim',
      'run',
    ])
  })

  it('drops entries without a usable duration', () => {
    const timeline = buildRaceTimeline({
      activities: [],
      segments: [segment({ duration_s: null }), segment({ segment_index: 1, sport: 'run' })],
    })

    expect(timeline).toHaveLength(1)
  })

  it('returns nothing when there is no source at all', () => {
    expect(buildRaceTimeline({ activities: [], segments: [] })).toEqual([])
  })
})

describe('segmentLabel', () => {
  it('labels unknown sports as-is', () => {
    expect(segmentLabel('kayak', 0, ['kayak'])).toBe('kayak')
  })
})

describe('resolveRaceElapsed', () => {
  it('prefers the official chrono over the watch', () => {
    const timeline = buildRaceTimeline({ activities: [], segments: FULL_SEGMENTS })

    const elapsed = resolveRaceElapsed({
      timeline,
      race: RACE,
      results: { ...emptyResults, official_time_s: 9100 },
    })

    expect(elapsed).toMatchObject({ totalS: 9100, source: 'official', deltaS: 100 })
  })

  it('falls back on the watch and computes the gap to the target', () => {
    const timeline = buildRaceTimeline({ activities: [], segments: FULL_SEGMENTS })

    expect(resolveRaceElapsed({ timeline, race: RACE, results: null })).toMatchObject({
      totalS: 9000,
      source: 'garmin',
      deltaS: 0,
    })
  })

  it('has no delta without a target time', () => {
    const elapsed = resolveRaceElapsed({
      timeline: buildRaceTimeline({ activities: [], segments: FULL_SEGMENTS }),
      race: { ...RACE, target_time_seconds: null },
      results: null,
    })

    expect(elapsed.deltaS).toBeNull()
  })
})

describe('expectedSharePct', () => {
  it('derives the expected split from the legs', () => {
    const shares = expectedSharePct(RACE)

    expect(Math.round(shares.bike ?? 0)).toBe(52)
    expect(Object.values(shares).reduce((a, b) => a + b, 0)).toBeCloseTo(100, 5)
  })

  it('returns nothing for a race without usable legs', () => {
    expect(expectedSharePct({ ...RACE, legs: null })).toEqual({})
    expect(expectedSharePct({ ...RACE, legs: [{ discipline: 'kayak', distance_km: 5 }] })).toEqual(
      {}
    )
  })
})

describe('summarizePreparation', () => {
  it('counts only the sessions of the preparation window', () => {
    const summary = summarizePreparation(
      [
        activity({ id: 'before', start_time: '2026-05-01T07:00:00Z' }),
        activity({ id: 'in', start_time: '2026-07-01T07:00:00Z', duration_s: 3600 }),
        activity({ id: 'race-day', start_time: '2026-08-22T07:00:00Z' }),
      ],
      '2026-06-22',
      '2026-08-22'
    )

    expect(summary).toMatchObject({ sessions: 1, durationS: 3600, weeks: 9 })
  })

  it('accepts a race without a preparation start date', () => {
    const summary = summarizePreparation(
      [activity({ start_time: '2026-07-01T07:00:00Z' })],
      null,
      '2026-08-22'
    )

    expect(summary.sessions).toBe(1)
    expect(summary.weeks).toBe(0)
  })
})

describe('timeBySport / compareRaces', () => {
  it('excludes transitions and compares discipline by discipline', () => {
    const current = buildRaceTimeline({ activities: [], segments: FULL_SEGMENTS })
    const previous = buildRaceTimeline({
      activities: [],
      segments: [
        segment({ segment_index: 0, sport: 'swim', duration_s: 2000 }),
        segment({ segment_index: 1, sport: 'bike', duration_s: 4000, distance_m: 40000 }),
        segment({ segment_index: 2, sport: 'kayak', duration_s: 600 }),
      ],
    })

    expect(timeBySport(current)).toEqual({ swim: 1800, bike: 4200, run: 2700 })
    expect(compareRaces(current, previous)).toEqual([
      { sport: 'swim', label: 'Natation', currentS: 1800, previousS: 2000, deltaS: -200 },
      { sport: 'bike', label: 'Vélo', currentS: 4200, previousS: 4000, deltaS: 200 },
    ])
  })

  it('reports no transition share without transitions', () => {
    expect(transitionSharePct([])).toBeNull()
    expect(
      transitionSharePct(
        buildRaceTimeline({ activities: [], segments: [segment({ sport: 'run' })] })
      )
    ).toBeNull()
  })
})

const emptyResults = {
  official_time_s: null,
  swim_time_s: null,
  t1_time_s: null,
  bike_time_s: null,
  t2_time_s: null,
  run_time_s: null,
  overall_rank: null,
  overall_finishers: null,
  category: null,
  category_rank: null,
  category_finishers: null,
  bib_number: null,
  results_url: null,
  weather: null,
  nutrition: null,
  gear: null,
  incidents: null,
  comment: null,
}

describe('buildRaceDebrief', () => {
  const timeline = buildRaceTimeline({ activities: [], segments: FULL_SEGMENTS })

  it('credits a target beaten and a preparation actually done', () => {
    const debrief = buildRaceDebrief({
      race: RACE,
      timeline,
      elapsed: resolveRaceElapsed({
        timeline,
        race: RACE,
        results: { ...emptyResults, official_time_s: 8400 },
      }),
      previousTimeline: null,
      preparation: { sessions: 42, durationS: 180_000, weeks: 9, distanceM: 500_000 },
    })

    expect(debrief.verdict).toContain('Objectif tenu')
    expect(debrief.strengths.join(' ')).toContain('42 séances')
    expect(debrief.tone).toBe('positive')
  })

  it('flags a missed target and slow transitions', () => {
    const slow = buildRaceTimeline({
      activities: [],
      segments: [
        segment({ segment_index: 0, sport: 'swim', duration_s: 1800 }),
        segment({ segment_index: 1, sport: 'transition', duration_s: 900, hr_avg: null }),
        segment({ segment_index: 2, sport: 'bike', duration_s: 4200, distance_m: 40000 }),
        segment({ segment_index: 3, sport: 'transition', duration_s: 600, hr_avg: null }),
        segment({
          segment_index: 4,
          sport: 'run',
          duration_s: 2700,
          distance_m: 10000,
          hr_avg: 120,
        }),
      ],
    })

    const debrief = buildRaceDebrief({
      race: RACE,
      timeline: slow,
      elapsed: resolveRaceElapsed({ timeline: slow, race: RACE, results: null }),
      previousTimeline: null,
      preparation: null,
    })

    expect(debrief.verdict).toContain('Objectif manqué')
    const improvements = debrief.improvements.join(' ')
    expect(improvements).toContain('transitions pèsent')
    expect(improvements).toContain('FC baisse')
    expect(debrief.tone).toBe('watch')
  })

  it('compares with the previous race of the same format', () => {
    const previous = buildRaceTimeline({
      activities: [],
      segments: [
        segment({ segment_index: 0, sport: 'swim', duration_s: 2100 }),
        segment({ segment_index: 1, sport: 'bike', duration_s: 4000, distance_m: 40000 }),
        segment({ segment_index: 2, sport: 'run', duration_s: 2700, distance_m: 10000 }),
      ],
    })

    const debrief = buildRaceDebrief({
      race: RACE,
      timeline,
      elapsed: resolveRaceElapsed({ timeline, race: RACE, results: null }),
      previousTimeline: previous,
      preparation: null,
    })

    expect(debrief.strengths.join(' ')).toContain('Natation : -5 min 00 s')
    expect(debrief.improvements.join(' ')).toContain('Vélo : +3 min 20 s')
  })

  it('degrades gracefully when almost nothing is known', () => {
    const debrief = buildRaceDebrief({
      race: { ...RACE, legs: null, target_time_seconds: null },
      timeline: [],
      elapsed: { totalS: 0, source: 'garmin', targetS: null, deltaS: null },
      previousTimeline: null,
      preparation: null,
    })

    expect(debrief.verdict).toContain('Saisis un temps objectif')
    expect(debrief.strengths).toHaveLength(1)
    expect(debrief.improvements).toHaveLength(1)
  })

  it('salutes a pacing aligned with the format', () => {
    const debrief = buildRaceDebrief({
      race: RACE,
      timeline,
      elapsed: resolveRaceElapsed({ timeline, race: RACE, results: null }),
      previousTimeline: null,
      preparation: null,
    })

    expect(debrief.strengths.join(' ')).toContain('Répartition du temps conforme')
  })
})

describe('race clocks', () => {
  it('formats a race time to the second', async () => {
    const { formatRaceClock } = await import('@/lib/coach/race-analysis')

    expect(formatRaceClock(9130)).toBe('2:32:10')
    expect(formatRaceClock(1930)).toBe('32:10')
    expect(formatRaceClock(null)).toBe('—')
    expect(formatRaceClock(0)).toBe('—')
  })

  it('formats a signed delta', async () => {
    const { formatClockDelta } = await import('@/lib/coach/race-analysis')

    expect(formatClockDelta(-252)).toBe('-4:12')
    expect(formatClockDelta(38)).toBe('+0:38')
    expect(formatClockDelta(0)).toBe('=')
    expect(formatClockDelta(null)).toBe('—')
  })

  it('parses the shapes an athlete actually types', async () => {
    const { parseRaceClock } = await import('@/lib/coach/race-analysis')

    expect(parseRaceClock('2:32:10')).toBe(9130)
    expect(parseRaceClock('32:10')).toBe(1930)
    expect(parseRaceClock('1h12')).toBe(4320)
    expect(parseRaceClock('1h12m30s')).toBe(4350)
    expect(parseRaceClock('9130')).toBe(9130)
    expect(parseRaceClock('  ')).toBeNull()
    expect(parseRaceClock('deux heures')).toBeNull()
    expect(parseRaceClock('2:aa')).toBeNull()
  })
})

describe('summarizeRaceHistory', () => {
  const olderRace: RaceGoalRow = {
    ...RACE,
    id: 'race-0',
    race_date: '2025-09-01',
    name: 'Premier triathlon',
    target_time_seconds: null,
  }

  const activitiesByRace = {
    'race-0': [activity({ id: 'a0', garmin_activity_id: 10, duration_s: 9600 })],
    'race-1': [activity({ id: 'a1', garmin_activity_id: 11, duration_s: 9000 })],
  }

  it('orders races from the most recent and measures the progress', async () => {
    const { summarizeRaceHistory } = await import('@/lib/coach/race-analysis')

    const history = summarizeRaceHistory({
      races: [RACE, olderRace],
      activitiesByRace,
      segmentsByActivity: {},
      resultsByRace: {},
    })

    expect(history.map((entry) => entry.raceGoalId)).toEqual(['race-1', 'race-0'])
    expect(history[0]).toMatchObject({ elapsedS: 9000, previousDeltaS: -600, targetDeltaS: 0 })
    expect(history[1]?.previousDeltaS).toBeNull()
  })

  it('prefers the official time and skips races without activities', async () => {
    const { summarizeRaceHistory } = await import('@/lib/coach/race-analysis')

    const history = summarizeRaceHistory({
      races: [RACE, olderRace],
      activitiesByRace: { 'race-1': activitiesByRace['race-1'] },
      segmentsByActivity: { 11: FULL_SEGMENTS },
      resultsByRace: { 'race-1': { ...emptyResults, official_time_s: 8888 } },
    })

    expect(history).toHaveLength(1)
    expect(history[0]).toMatchObject({ elapsedS: 8888, source: 'official' })
  })

  it('skips a race whose activities have no usable duration', async () => {
    const { summarizeRaceHistory } = await import('@/lib/coach/race-analysis')

    const history = summarizeRaceHistory({
      races: [RACE],
      activitiesByRace: { 'race-1': [activity({ id: 'a1', duration_s: 0 })] },
      segmentsByActivity: {},
      resultsByRace: {},
    })

    expect(history).toEqual([])
  })
})

describe('buildRaceSalute', () => {
  const elapsed = (totalS: number, targetS: number | null = RACE.target_time_seconds) => ({
    totalS,
    source: 'garmin' as const,
    targetS,
    deltaS: targetS === null ? null : totalS - targetS,
  })
  const finisher = [activity({ distance_m: 51_500, duration_s: 8700 })]

  it('félicite un objectif tenu, avec l’écart en clair', () => {
    const salute = buildRaceSalute({
      race: RACE,
      activities: finisher,
      elapsed: elapsed(8700),
      previousDeltaS: null,
      isFirstRace: false,
    })
    expect(salute.tone).toBe('cheer')
    expect(salute.headline).toContain('Objectif tenu')
    expect(salute.figure).toBe('2:25:00')
  })

  it('fête la première course avant toute comparaison', () => {
    const salute = buildRaceSalute({
      race: RACE,
      activities: finisher,
      elapsed: elapsed(9600),
      previousDeltaS: null,
      isFirstRace: true,
    })
    expect(salute.tone).toBe('cheer')
    expect(salute.headline).toContain('Première course')
  })

  it('salue un progrès sur la course précédente quand la cible est manquée de peu', () => {
    const salute = buildRaceSalute({
      race: RACE,
      activities: finisher,
      elapsed: elapsed(9300),
      previousDeltaS: -240,
      isFirstRace: false,
    })
    expect(salute.tone).toBe('cheer')
    expect(salute.headline).toContain('de mieux')
  })

  it('reste factuel sans temps visé ni course précédente', () => {
    const salute = buildRaceSalute({
      race: RACE,
      activities: finisher,
      elapsed: elapsed(9300, null),
      previousDeltaS: null,
      isFirstRace: false,
    })
    expect(salute.tone).toBe('neutral')
    expect(salute.headline).toBe('Course bouclée.')
  })

  it('ne félicite jamais une course écourtée, même si c’est la première', () => {
    // La seule erreur vraiment coûteuse ici : un « Bravo » à quelqu'un qui a abandonné.
    const salute = buildRaceSalute({
      race: RACE,
      activities: [activity({ distance_m: 33_000, duration_s: 6000 })],
      elapsed: elapsed(6000),
      previousDeltaS: -600,
      isFirstRace: true,
    })
    expect(salute.tone).toBe('tender')
    expect(salute.headline).not.toContain('Bravo')
  })

  it('prend un ton attentionné quand la cible est très largement manquée', () => {
    const salute = buildRaceSalute({
      race: RACE,
      activities: finisher,
      elapsed: elapsed(11_000),
      previousDeltaS: null,
      isFirstRace: false,
    })
    expect(salute.tone).toBe('tender')
  })

  it('ne conclut pas à une course écourtée sans distance exploitable', () => {
    const salute = buildRaceSalute({
      race: { ...RACE, total_distance_km: null, legs: null },
      activities: [activity({ distance_m: 0 })],
      elapsed: elapsed(8700),
      previousDeltaS: null,
      isFirstRace: false,
    })
    expect(salute.tone).toBe('cheer')
  })
})
