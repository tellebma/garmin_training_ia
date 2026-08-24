import {
  formatDistanceFromMeters,
  formatDuration,
  formatSpeedForSport,
} from '@/lib/dashboard/format'
import type { Sport } from '@/lib/dashboard/types'
import type { ProjectedRoute } from './story-layout'

/**
 * Un segment d'activité multisport, tel que le worker le persiste dans
 * `activity_segments` : une ligne par discipline (et par transition), dans
 * l'ordre de l'épreuve.
 */
export interface StorySegment {
  readonly sport: string
  readonly duration_s: number | null
  readonly distance_m: number | null
  readonly elevation_gain_m: number | null
  readonly hr_avg: number | null
  readonly pace_avg_s_per_km: number | null
}

/** Ligne prête à dessiner : un bloc « discipline » du calque. */
export interface StorySegmentLine {
  readonly key: string
  readonly sport: string
  readonly label: string
  readonly color: string
  /** « 1:10:00 · 40,0 km · 34,3 km/h » — déjà formaté, unités comprises. */
  readonly value: string
}

const SEGMENT_LABELS: Readonly<Record<string, string>> = {
  swim: 'Natation',
  bike: 'Vélo',
  run: 'Course',
  transition: 'Transition',
}

/**
 * Une teinte par discipline, fixe : c'est elle qui rend les trois efforts
 * distinguables d'un coup d'œil, sur la pile de métriques comme sur le tracé.
 * La couleur d'accent choisie par l'utilisateur reste celle des autres gabarits.
 */
export const SEGMENT_COLORS: Readonly<Record<string, string>> = {
  swim: '#38bdf8',
  bike: '#fbbf24',
  run: '#a3e635',
  transition: 'rgba(255,255,255,0.55)',
}

const DEFAULT_SEGMENT_COLOR = '#e2e8f0'

/** Nombre de lignes au-delà duquel le sticker devient illisible. */
export const MAX_SEGMENT_LINES = 6

export function segmentSportLabel(sport: string): string {
  return SEGMENT_LABELS[sport] ?? sport
}

export function segmentSportColor(sport: string): string {
  return SEGMENT_COLORS[sport] ?? DEFAULT_SEGMENT_COLOR
}

function isFiniteNumber(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function knownPaceSport(sport: string): Sport {
  // `formatSpeedForSport` n'accepte que les sports canoniques ; hors nage et
  // course, l'unité pertinente est le km/h, que `bike` fournit.
  return sport === 'swim' || sport === 'run' ? sport : 'bike'
}

/**
 * Allure (nage, course) ou vitesse (le reste) du segment. `distanceM` et
 * `durationS` sont déjà validés par l'appelant, ce qui rend le calcul total :
 * l'allure persistée si Garmin l'a fournie, sinon distance / durée.
 */
function segmentPace(segment: StorySegment, distanceM: number, durationS: number): string {
  const speedMs =
    isFiniteNumber(segment.pace_avg_s_per_km) && segment.pace_avg_s_per_km > 0
      ? 1000 / segment.pace_avg_s_per_km
      : distanceM / durationS
  return formatSpeedForSport(knownPaceSport(segment.sport), speedMs)
}

/**
 * Compose une ligne par segment : durée, puis distance et allure quand elles
 * existent. Une transition n'a qu'une durée — l'afficher avec « — km » la
 * rendrait plus bruyante qu'informative.
 */
export function buildStorySegmentLines(segments: readonly StorySegment[]): StorySegmentLine[] {
  return segments
    .filter((segment) => isFiniteNumber(segment.duration_s) && segment.duration_s > 0)
    .slice(0, MAX_SEGMENT_LINES)
    .map((segment, index) => {
      const parts = [formatDuration(segment.duration_s)]
      if (isFiniteNumber(segment.distance_m) && segment.distance_m > 0) {
        parts.push(
          formatDistanceFromMeters(segment.distance_m),
          segmentPace(segment, segment.distance_m, segment.duration_s ?? 0)
        )
      }
      return {
        key: `${segment.sport}-${String(index)}`,
        sport: segment.sport,
        label: segmentSportLabel(segment.sport),
        color: segmentSportColor(segment.sport),
        value: parts.join(' · '),
      }
    })
}

/** Le calque « disciplines » n'a de sens qu'avec au moins deux efforts distincts. */
export function hasDistinctDisciplines(segments: readonly StorySegment[]): boolean {
  const disciplines = new Set(
    segments.filter((segment) => segment.sport !== 'transition').map((segment) => segment.sport)
  )
  return disciplines.size >= 2
}

export interface RouteSlice {
  readonly sport: string
  readonly color: string
  readonly points: ProjectedRoute['points']
}

/**
 * Découpe un tracé projeté en tronçons par discipline.
 *
 * Le rattachement se fait sur le temps écoulé : les segments donnent des durées
 * cumulées, chaque point du tracé porte son `elapsed_s`. Les tronçons se
 * chevauchent d'un point pour que le trait reste continu d'une discipline à
 * l'autre. Renvoie une liste vide dès que le découpage n'est pas fiable (pas de
 * temps sur les points, segments sans durée, un seul tronçon non vide) — le
 * renderer retombe alors sur un tracé d'une seule couleur.
 */
export function sliceRouteBySegments(
  route: ProjectedRoute,
  segments: readonly StorySegment[]
): RouteSlice[] {
  const usable = segments.filter(
    (segment) => isFiniteNumber(segment.duration_s) && segment.duration_s > 0
  )
  if (usable.length < 2 || route.points.length < 2) return []
  const elapsed = route.elapsed
  if (elapsed.length !== route.points.length) return []
  if (!elapsed.every(isFiniteNumber)) return []

  const slices: RouteSlice[] = []
  let cursor = 0
  let boundary = 0
  for (const [index, segment] of usable.entries()) {
    boundary += segment.duration_s ?? 0
    const isLast = index === usable.length - 1
    let end = cursor
    while (end < elapsed.length - 1 && (elapsed[end] ?? 0) < boundary) end++
    if (isLast) end = elapsed.length - 1
    if (end > cursor) {
      slices.push({
        sport: segment.sport,
        color: segmentSportColor(segment.sport),
        points: route.points.slice(cursor, end + 1),
      })
      // Chevauchement d'un point : sans lui, un trou apparaît à la jointure.
      cursor = end
    }
  }
  return slices.length >= 2 ? slices : []
}
