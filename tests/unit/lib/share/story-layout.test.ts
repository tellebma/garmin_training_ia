import { beforeAll, describe, expect, it } from 'vitest'
import {
  buildElevationProfile,
  buildStoryMetrics,
  compactSamplesForStory,
  computeStoryLayout,
  defaultMetricKeys,
  findStoryBlock,
  metricsCapForView,
  projectRoute,
  STORY_SIZES,
  STORY_TRANSFERRED_POINTS,
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
  it('retient au plus le plafond du gabarit, dans l’ordre d’importance', () => {
    const metrics = buildStoryMetrics(BIKE, 'bike')
    expect(defaultMetricKeys(metrics, 3)).toEqual(['distance', 'duration', 'elevation'])
    expect(defaultMetricKeys(metrics, 4)).toEqual(['distance', 'duration', 'elevation', 'pace'])
  })

  it('ne renvoie rien quand le gabarit n’affiche aucune métrique', () => {
    expect(defaultMetricKeys(buildStoryMetrics(BIKE, 'bike'), 0)).toEqual([])
  })
})

describe('storyFileName', () => {
  // Le nom de fichier suit le jour **local** : on fige le fuseau pour que le test soit
  // stable, et on garde un oracle indépendant (`en-CA` ⇒ AAAA-MM-JJ local) au cas où la
  // plateforme ignore la variable.
  const localDay = (iso: string) => new Date(iso).toLocaleDateString('en-CA')

  beforeAll(() => {
    process.env.TZ = 'Europe/Paris'
  })

  it('construit un nom lisible depuis la date et le sport', () => {
    expect(storyFileName(BIKE, 'trace')).toBe(
      `garmin-coach-${localDay(BIKE.start_time)}-bike-trace.png`
    )
  })

  it('date le fichier sur le jour local et non sur UTC', () => {
    // 23 h 30 UTC le 28 = déjà le 29 à Paris : `toISOString()` daterait le fichier de la veille.
    const lateNight: StoryActivity = { ...BIKE, start_time: '2026-07-28T23:30:00.000Z' }
    expect(storyFileName(lateNight, 'trace')).toBe(
      `garmin-coach-${localDay(lateNight.start_time)}-bike-trace.png`
    )
  })

  it('retombe sur un nom générique si la date est invalide', () => {
    expect(storyFileName({ ...BIKE, start_time: 'nope' }, 'stats')).toBe(
      'garmin-coach-activite-bike-stats.png'
    )
  })

  it('assainit les sports exotiques', () => {
    expect(storyFileName({ ...BIKE, sport: 'Trail Running' }, 'minimal')).toBe(
      `garmin-coach-${localDay(BIKE.start_time)}-trail-running-minimal.png`
    )
  })
})

describe('computeStoryLayout', () => {
  const kinds = (view: Parameters<typeof computeStoryLayout>[0], count = 3) =>
    computeStoryLayout(view, 'story', count).blocks.map((block) => block.kind)

  it('réserve tout le cadre au tracé en vue minimal', () => {
    const layout = computeStoryLayout('minimal', 'story', 6)
    expect(layout.blocks.map((b) => b.kind)).toEqual(['route'])
    expect(findStoryBlock(layout, 'route')?.height).toBeGreaterThan(1000)
    expect(layout.scale).toBe(1)
  })

  it('empile tracé puis ligne de métriques en vue trace', () => {
    expect(kinds('trace')).toEqual(['title', 'route', 'metricsRow', 'brand'])
  })

  it('empile métriques puis tracé en vue stats-trace', () => {
    expect(kinds('stats-trace')).toEqual(['title', 'metricsStack', 'route', 'brand'])
  })

  it('utilise le profil comme visuel en vue profil', () => {
    expect(kinds('profil')).toEqual(['title', 'elevation', 'metricsRow', 'brand'])
  })

  it('n’a aucun visuel en vue stats', () => {
    expect(kinds('stats')).toEqual(['title', 'metricsStack', 'brand'])
  })

  it('retire titre et signature à la demande', () => {
    const layout = computeStoryLayout('trace', 'story', 3, { showTitle: false, showBrand: false })
    expect(layout.blocks.map((b) => b.kind)).toEqual(['route', 'metricsRow'])
  })

  it('retire le bloc de métriques quand il n’y en a aucune', () => {
    expect(kinds('trace', 0)).toEqual(['title', 'route', 'brand'])
    expect(kinds('stats', 0)).toEqual(['title', 'brand'])
  })

  it('centre la pile verticalement dans la zone sûre', () => {
    const layout = computeStoryLayout('trace', 'story', 3)
    const first = layout.blocks[0]
    const last = layout.blocks.at(-1)
    expect(first).toBeDefined()
    expect(last).toBeDefined()
    if (!first || !last) return
    const marginTop = first.box.y - 260
    const marginBottom = STORY_SIZES.story.height - 300 - (last.box.y + last.box.height)
    expect(marginTop).toBeGreaterThan(0)
    expect(Math.abs(marginTop - marginBottom)).toBeLessThan(1)
  })

  it('empile les blocs sans chevauchement, dans la zone sûre', () => {
    const layout = computeStoryLayout('stats-trace', 'story', 4)
    let previousBottom = 260
    for (const { box } of layout.blocks) {
      expect(box.y).toBeGreaterThanOrEqual(previousBottom)
      expect(box.x).toBe(88)
      expect(box.width).toBe(STORY_SIZES.story.width - 176)
      previousBottom = box.y + box.height
    }
    expect(previousBottom).toBeLessThanOrEqual(STORY_SIZES.story.height - 300 + 0.001)
  })

  it('réduit toute la pile quand elle déborde (format carré)', () => {
    const layout = computeStoryLayout('trace', 'square', 3)
    expect(layout.scale).toBeLessThan(1)
    const last = layout.blocks.at(-1)
    expect(last).toBeDefined()
    if (!last) return
    expect(last.box.y + last.box.height).toBeLessThanOrEqual(STORY_SIZES.square.height - 88)
  })

  it('ne réduit pas une pile qui tient déjà', () => {
    expect(computeStoryLayout('trace', 'story', 3).scale).toBe(1)
  })

  it('renvoie une pile vide quand tout est masqué en vue stats sans métrique', () => {
    const layout = computeStoryLayout('stats', 'story', 0, { showTitle: false, showBrand: false })
    expect(layout.blocks).toEqual([])
    expect(layout.scale).toBe(1)
  })
})

describe('metricsCapForView', () => {
  it('limite la ligne à 3 métriques et la pile à 4', () => {
    expect(metricsCapForView('trace')).toBe(3)
    expect(metricsCapForView('profil')).toBe(3)
    expect(metricsCapForView('stats')).toBe(4)
    expect(metricsCapForView('stats-trace')).toBe(4)
    expect(metricsCapForView('minimal')).toBe(0)
  })

  it('n’affiche jamais plus de métriques que le plafond du gabarit', () => {
    const layout = computeStoryLayout('trace', 'story', 9)
    const row = findStoryBlock(layout, 'metricsRow')
    const forThree = findStoryBlock(computeStoryLayout('trace', 'story', 3), 'metricsRow')
    expect(row?.height).toBe(forThree?.height)
  })
})

describe('findStoryBlock', () => {
  it('renvoie null pour un bloc absent', () => {
    expect(findStoryBlock(computeStoryLayout('stats', 'story', 3), 'route')).toBeNull()
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
      {
        latitude: 45.123_456_789,
        longitude: 4.987_654_321,
        distance_m: 10.7,
        elevation_m: 220.4,
        elapsed_s: 12.4,
      },
      { latitude: null, longitude: null, distance_m: 20, elevation_m: 240.6 },
      { latitude: 45.2, longitude: 5, distance_m: null, elevation_m: null },
    ])
    // `elapsed_s` accompagne chaque point : c'est lui qui rattache le tracé aux
    // disciplines d'un multisport. Absent des samples, il vaut `null`.
    expect(sets.route).toEqual([
      { latitude: 45.123_46, longitude: 4.987_65, elapsed_s: 12 },
      { latitude: 45.2, longitude: 5, elapsed_s: null },
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
    // Budget serré : ces points doublent ceux déjà transmis à la carte dans le payload RSC.
    expect(sets.route).toHaveLength(STORY_TRANSFERRED_POINTS)
    expect(sets.elevation).toHaveLength(STORY_TRANSFERRED_POINTS)
    expect(STORY_TRANSFERRED_POINTS).toBeLessThanOrEqual(300)
  })
})
