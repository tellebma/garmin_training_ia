import { describe, expect, it } from 'vitest'
import {
  buildStorySegmentLines,
  hasDistinctDisciplines,
  MAX_SEGMENT_LINES,
  segmentSportColor,
  segmentSportLabel,
  sliceRouteBySegments,
  type StorySegment,
} from '@/lib/share/story-segments'
import type { ProjectedRoute } from '@/lib/share/story-layout'

function segment(overrides: Partial<StorySegment> = {}): StorySegment {
  return {
    sport: 'bike',
    duration_s: 3600,
    distance_m: 30_000,
    elevation_gain_m: 200,
    hr_avg: 140,
    pace_avg_s_per_km: null,
    ...overrides,
  }
}

const TRIATHLON: StorySegment[] = [
  segment({ sport: 'swim', duration_s: 1500, distance_m: 1500, elevation_gain_m: null }),
  segment({ sport: 'transition', duration_s: 90, distance_m: null, elevation_gain_m: null }),
  segment({ sport: 'bike', duration_s: 4200, distance_m: 40_000 }),
  segment({ sport: 'run', duration_s: 3000, distance_m: 10_000, elevation_gain_m: 40 }),
]

describe('buildStorySegmentLines', () => {
  it('compose une ligne par discipline, unités comprises', () => {
    const lines = buildStorySegmentLines(TRIATHLON)

    expect(lines.map((line) => line.label)).toEqual(['Natation', 'Transition', 'Vélo', 'Course'])
    expect(lines[0]?.value).toBe('25min · 1.5 km · 1:40 /100m')
    expect(lines[2]?.value).toBe('1h10 · 40 km · 34.3 km/h')
    expect(lines[3]?.value).toBe('50min · 10 km · 5:00 /km')
  })

  it('réduit une transition à sa durée', () => {
    // Sans distance, afficher « — km » ferait du bruit plutôt que de l'information.
    const [line] = buildStorySegmentLines([
      segment({ sport: 'transition', duration_s: 90, distance_m: null }),
    ])

    expect(line?.value).toBe('1min')
  })

  it('ignore un segment sans durée exploitable', () => {
    const lines = buildStorySegmentLines([
      segment({ sport: 'swim', duration_s: null }),
      segment({ sport: 'run', duration_s: 0 }),
      segment({ sport: 'bike', duration_s: 600 }),
    ])

    expect(lines).toHaveLength(1)
    expect(lines[0]?.sport).toBe('bike')
  })

  it('borne le nombre de lignes pour rester lisible', () => {
    const many = Array.from({ length: MAX_SEGMENT_LINES + 3 }, () => segment())

    expect(buildStorySegmentLines(many)).toHaveLength(MAX_SEGMENT_LINES)
  })

  it('utilise l’allure persistée quand elle existe', () => {
    const [line] = buildStorySegmentLines([
      segment({ sport: 'run', duration_s: 3000, distance_m: 10_000, pace_avg_s_per_km: 270 }),
    ])

    expect(line?.value).toContain('4:30 /km')
  })

  it('dégrade proprement sur un sport inconnu', () => {
    const [line] = buildStorySegmentLines([segment({ sport: 'kayaking', distance_m: null })])

    expect(line?.label).toBe('kayaking')
    expect(segmentSportLabel('kayaking')).toBe('kayaking')
    expect(segmentSportColor('kayaking')).toBe(segmentSportColor('inconnu'))
  })
})

describe('hasDistinctDisciplines', () => {
  it('reconnaît un multisport', () => {
    expect(hasDistinctDisciplines(TRIATHLON)).toBe(true)
  })

  it('ne compte pas les transitions comme une discipline', () => {
    expect(
      hasDistinctDisciplines([
        segment({ sport: 'run' }),
        segment({ sport: 'transition', distance_m: null }),
      ])
    ).toBe(false)
  })

  it('reste faux sans segment', () => {
    expect(hasDistinctDisciplines([])).toBe(false)
  })
})

function route(elapsed: readonly number[]): ProjectedRoute {
  return {
    points: elapsed.map((_, index) => [index * 10, index * 5] as const),
    elapsed,
  }
}

describe('sliceRouteBySegments', () => {
  it('découpe le tracé sur le temps écoulé, un tronçon par discipline', () => {
    const segments = [
      segment({ sport: 'swim', duration_s: 100 }),
      segment({ sport: 'bike', duration_s: 100 }),
      segment({ sport: 'run', duration_s: 100 }),
    ]

    const slices = sliceRouteBySegments(route([0, 50, 100, 150, 200, 250, 300]), segments)

    expect(slices.map((slice) => slice.sport)).toEqual(['swim', 'bike', 'run'])
    // Les tronçons se chevauchent d'un point : sans cela, le trait se troue à
    // chaque jointure de discipline.
    expect(slices[0]?.points.at(-1)).toEqual(slices[1]?.points[0])
    expect(slices[1]?.points.at(-1)).toEqual(slices[2]?.points[0])
    // Le dernier tronçon va jusqu'au bout du tracé, même si les durées cumulées
    // des segments tombent avant le dernier point.
    expect(slices.at(-1)?.points.at(-1)).toEqual([60, 30])
  })

  it('renonce quand les points ne portent pas de temps', () => {
    const slices = sliceRouteBySegments(route([Number.NaN, Number.NaN, Number.NaN]), [
      segment({ sport: 'swim', duration_s: 100 }),
      segment({ sport: 'run', duration_s: 100 }),
    ])

    expect(slices).toEqual([])
  })

  it('renonce sur une activité simple', () => {
    expect(sliceRouteBySegments(route([0, 10, 20]), [segment({ sport: 'run' })])).toEqual([])
    expect(sliceRouteBySegments(route([0, 10, 20]), [])).toEqual([])
  })

  it('renonce sur un tracé trop court', () => {
    expect(
      sliceRouteBySegments({ points: [[0, 0]], elapsed: [0] }, [
        segment({ sport: 'swim', duration_s: 10 }),
        segment({ sport: 'run', duration_s: 10 }),
      ])
    ).toEqual([])
  })

  it('renonce si un seul tronçon reçoit des points', () => {
    // Toute la trace tombe dans la première discipline : la colorier par segment
    // n'apporterait rien et masquerait le fallback monochrome.
    const slices = sliceRouteBySegments(route([0, 1, 2, 3]), [
      segment({ sport: 'swim', duration_s: 10_000 }),
      segment({ sport: 'run', duration_s: 10 }),
    ])

    expect(slices).toEqual([])
  })
})
