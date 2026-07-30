import { describe, expect, it } from 'vitest'
import {
  buildElevationProfile,
  buildStoryMetrics,
  compactSamplesForStory,
  computeStoryLayout,
  defaultMetricKeys,
  MAX_STORY_METRICS,
  projectRoute,
  STORY_SIZES,
  storyFileName,
  type Box,
  type StoryActivity,
} from '@/lib/share/story-layout'

const BOX: Box = { x: 100, y: 200, width: 800, height: 400 }

const BIKE: StoryActivity = {
  start_time: '2026-07-28T07:12:00.000Z',
  sport: 'bike',
  duration_s: 5820,
  distance_m: 42_350,
  elevation_gain_m: 780,
  tss: 186,
  hr_avg: 148,
  hr_max: 176,
  power_avg: 212,
  pace_avg_s_per_km: null,
  calories: 1240,
}

const EMPTY: StoryActivity = {
  start_time: '2026-07-28T07:12:00.000Z',
  sport: 'swim',
  duration_s: null,
  distance_m: null,
  elevation_gain_m: null,
  tss: null,
  hr_avg: null,
  hr_max: null,
  power_avg: null,
  pace_avg_s_per_km: null,
  calories: null,
}

describe('buildStoryMetrics', () => {
  it('ordonne les métriques et libelle la vitesse pour le vélo', () => {
    const metrics = buildStoryMetrics(BIKE, 'bike')
    expect(metrics.map((m) => m.key)).toEqual([
      'distance',
      'duration',
      'elevation',
      'pace',
      'hr_avg',
      'hr_max',
      'power',
      'tss',
      'calories',
    ])
    expect(metrics.find((m) => m.key === 'pace')).toEqual({
      key: 'pace',
      label: 'Vitesse',
      value: '26.2 km/h',
    })
    expect(metrics.find((m) => m.key === 'distance')?.value).toBe('42 km')
    expect(metrics.find((m) => m.key === 'duration')?.value).toBe('1h37')
  })

  it('libelle « Allure » et utilise pace_avg_s_per_km en course', () => {
    const run: StoryActivity = { ...BIKE, sport: 'run', pace_avg_s_per_km: 285 }
    const pace = buildStoryMetrics(run, 'run').find((m) => m.key === 'pace')
    expect(pace).toEqual({ key: 'pace', label: 'Allure', value: '4:45 /km' })
  })

  it('omet toute métrique absente ou nulle', () => {
    expect(buildStoryMetrics(EMPTY, 'swim')).toEqual([])
  })

  it('omet la vitesse quand la distance existe sans durée exploitable', () => {
    const broken: StoryActivity = { ...EMPTY, distance_m: 1000, duration_s: 0 }
    expect(buildStoryMetrics(broken, 'swim').map((m) => m.key)).toEqual(['distance'])
  })
})

describe('defaultMetricKeys', () => {
  it('retient au plus MAX_STORY_METRICS clés', () => {
    const keys = defaultMetricKeys(buildStoryMetrics(BIKE, 'bike'))
    expect(keys).toHaveLength(MAX_STORY_METRICS)
    expect(keys[0]).toBe('distance')
  })
})

describe('storyFileName', () => {
  it('construit un nom lisible depuis la date et le sport', () => {
    expect(storyFileName(BIKE, 'trace')).toBe('garmin-coach-2026-07-28-bike-trace.png')
  })

  it('retombe sur un nom générique si la date est invalide', () => {
    expect(storyFileName({ ...BIKE, start_time: 'nope' }, 'stats')).toBe(
      'garmin-coach-activite-bike-stats.png'
    )
  })

  it('assainit les sports exotiques', () => {
    expect(storyFileName({ ...BIKE, sport: 'Trail Running' }, 'minimal')).toBe(
      'garmin-coach-2026-07-28-trail-running-minimal.png'
    )
  })
})

describe('computeStoryLayout', () => {
  it('réserve tout le cadre au visuel en vue minimal', () => {
    const layout = computeStoryLayout('minimal', 'story', 6)
    expect(layout.header).toBeNull()
    expect(layout.metrics).toBeNull()
    expect(layout.brand).toBeNull()
    expect(layout.visual).not.toBeNull()
    expect(layout.visual?.height).toBeGreaterThan(1000)
  })

  it('supprime le visuel en vue stats et centre la grille', () => {
    const layout = computeStoryLayout('stats', 'story', 6)
    expect(layout.visual).toBeNull()
    expect(layout.metrics).not.toBeNull()
    expect(layout.large).toBe(true)
    expect(layout.metrics?.y).toBeGreaterThan(
      (layout.header?.y ?? 0) + (layout.header?.height ?? 0)
    )
  })

  it('garde un visuel exploitable au format carré', () => {
    const layout = computeStoryLayout('trace', 'square', 6)
    expect(layout.visual?.height).toBeGreaterThan(200)
    expect(layout.columns).toBe(3)
  })

  it('choisit un nombre de colonnes qui remplit la dernière ligne', () => {
    expect(computeStoryLayout('trace', 'square', 4).columns).toBe(2)
    expect(computeStoryLayout('trace', 'square', 5).columns).toBe(3)
    expect(computeStoryLayout('trace', 'story', 6).columns).toBe(2)
    expect(computeStoryLayout('trace', 'story', 1).columns).toBe(1)
  })

  it('n’émet pas de grille quand il n’y a aucune métrique', () => {
    const layout = computeStoryLayout('trace', 'story', 0)
    expect(layout.metrics).toBeNull()
    expect(layout.visual).not.toBeNull()
  })

  it('n’émet pas de grille en vue stats sans métrique', () => {
    const layout = computeStoryLayout('stats', 'story', 0)
    expect(layout.metrics).toBeNull()
    expect(layout.visual).toBeNull()
    expect(layout.brand).not.toBeNull()
  })

  it('garde tous les blocs dans la zone sûre du canvas', () => {
    const layout = computeStoryLayout('trace', 'story', 6)
    const size = STORY_SIZES.story
    for (const box of [layout.header, layout.visual, layout.metrics, layout.brand]) {
      expect(box).not.toBeNull()
      if (!box) continue
      expect(box.x).toBeGreaterThanOrEqual(0)
      expect(box.y).toBeGreaterThanOrEqual(0)
      expect(box.x + box.width).toBeLessThanOrEqual(size.width)
      expect(box.y + box.height).toBeLessThanOrEqual(size.height)
    }
  })

  it('supprime le visuel quand les métriques ne laissent pas la place', () => {
    // 12 métriques au format carré : la grille mange tout l'espace disponible.
    expect(computeStoryLayout('trace', 'square', 12).visual).toBeNull()
  })
})

describe('projectRoute', () => {
  const square = [
    { latitude: 45, longitude: 4 },
    { latitude: 45.01, longitude: 4 },
    { latitude: 45.01, longitude: 4.02 },
    { latitude: 45, longitude: 4.02 },
  ]

  it('renvoie null en dessous de deux points géolocalisés', () => {
    expect(projectRoute([{ latitude: 45, longitude: 4 }], BOX)).toBeNull()
    expect(projectRoute([{ latitude: null, longitude: null }], BOX)).toBeNull()
  })

  it('renvoie null si tous les points sont confondus', () => {
    expect(
      projectRoute(
        [
          { latitude: 45, longitude: 4 },
          { latitude: 45, longitude: 4 },
        ],
        BOX
      )
    ).toBeNull()
  })

  it('tient dans la boîte et oriente le nord vers le haut', () => {
    const projected = projectRoute(square, BOX)
    expect(projected).not.toBeNull()
    if (!projected) return
    for (const [x, y] of projected.points) {
      expect(x).toBeGreaterThanOrEqual(BOX.x - 0.001)
      expect(x).toBeLessThanOrEqual(BOX.x + BOX.width + 0.001)
      expect(y).toBeGreaterThanOrEqual(BOX.y - 0.001)
      expect(y).toBeLessThanOrEqual(BOX.y + BOX.height + 0.001)
    }
    const [south, north] = projected.points
    expect(south?.[1]).toBeGreaterThan(north?.[1] ?? 0)
  })

  it('ignore les points sans coordonnées', () => {
    const projected = projectRoute([...square, { latitude: null, longitude: 4 }], BOX)
    expect(projected?.points).toHaveLength(square.length)
  })

  it('sous-échantillonne les traces très denses', () => {
    const dense = Array.from({ length: 4000 }, (_, i) => ({
      latitude: 45 + i / 100_000,
      longitude: 4 + i / 50_000,
    }))
    expect(projectRoute(dense, BOX)?.points.length).toBeLessThanOrEqual(900)
  })
})

describe('buildElevationProfile', () => {
  const samples = [
    { distance_m: 0, elevation_m: 100 },
    { distance_m: 1000, elevation_m: 300 },
    { distance_m: 2000, elevation_m: 150 },
  ]

  it('renvoie null en dessous de deux points d’altitude', () => {
    expect(buildElevationProfile([{ distance_m: 0, elevation_m: null }], BOX)).toBeNull()
  })

  it('place le sommet au point le plus haut et la base en bas de boîte', () => {
    const profile = buildElevationProfile(samples, BOX)
    expect(profile).not.toBeNull()
    if (!profile) return
    expect(profile.baselineY).toBe(BOX.y + BOX.height)
    expect(profile.maxElevation).toBe(300)
    expect(profile.minElevation).toBe(100)
    expect(profile.peak[1]).toBe(BOX.y)
    expect(profile.points[0]?.[0]).toBe(BOX.x)
    expect(profile.points.at(-1)?.[0]).toBe(BOX.x + BOX.width)
  })

  it('retombe sur l’index quand la distance manque', () => {
    const profile = buildElevationProfile(
      samples.map((s) => ({ ...s, distance_m: null })),
      BOX
    )
    expect(profile?.points.at(-1)?.[0]).toBe(BOX.x + BOX.width)
  })

  it('centre le profil quand l’altitude est constante', () => {
    const flat = buildElevationProfile(
      [
        { distance_m: 0, elevation_m: 100 },
        { distance_m: 1000, elevation_m: 100 },
      ],
      BOX
    )
    expect(flat?.points[0]?.[1]).toBe(BOX.y + BOX.height / 2)
  })
})

describe('compactSamplesForStory', () => {
  it('sépare trace et altitude en arrondissant', () => {
    const sets = compactSamplesForStory([
      { latitude: 45.123_456_789, longitude: 4.987_654_321, distance_m: 10.7, elevation_m: 220.4 },
      { latitude: null, longitude: null, distance_m: 20, elevation_m: 240.6 },
      { latitude: 45.2, longitude: 5, distance_m: null, elevation_m: null },
    ])
    expect(sets.route).toEqual([
      { latitude: 45.123_46, longitude: 4.987_65 },
      { latitude: 45.2, longitude: 5 },
    ])
    expect(sets.elevation).toEqual([
      { distance_m: 11, elevation_m: 220 },
      { distance_m: 20, elevation_m: 241 },
    ])
  })

  it('borne le nombre de points transmis au client', () => {
    const many = Array.from({ length: 5000 }, (_, i) => ({
      latitude: 45 + i / 100_000,
      longitude: 4,
      distance_m: i,
      elevation_m: 100 + i,
    }))
    const sets = compactSamplesForStory(many)
    expect(sets.route.length).toBeLessThanOrEqual(900)
    expect(sets.elevation.length).toBeLessThanOrEqual(900)
  })
})
