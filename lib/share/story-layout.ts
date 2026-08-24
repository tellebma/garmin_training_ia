import {
  formatDistanceFromMeters,
  formatDuration,
  formatSpeedForSport,
  paceUnitForSport,
} from '@/lib/dashboard/format'
import type { Sport } from '@/lib/dashboard/types'

/** Format de sortie du calque : story 9:16 ou carré 1:1 (post / feed). */
export type StoryFormat = 'story' | 'square'

/**
 * Gabarit du calque :
 * - `trace`       : grand tracé GPS puis une ligne de métriques
 * - `stats-trace` : métriques empilées en très gros puis un tracé plus petit
 * - `profil`      : profil altimétrique puis une ligne de métriques
 * - `stats`       : métriques seules (activités sans GPS : home-trainer, piscine…)
 * - `disciplines` : une ligne par discipline d'un multisport, puis le total
 * - `minimal`     : tracé seul, sans texte (calque à superposer librement)
 */
export type StoryView = 'trace' | 'stats-trace' | 'profil' | 'stats' | 'disciplines' | 'minimal'

/** Fond du PNG : transparent (vrai calque), sombre opaque, ou dégradé bas de vignette. */
export type StoryBackground = 'transparent' | 'dark' | 'gradient'

export interface StorySize {
  readonly width: number
  readonly height: number
}

export interface Box {
  readonly x: number
  readonly y: number
  readonly width: number
  readonly height: number
}

export interface StoryMetric {
  readonly key: string
  readonly label: string
  readonly value: string
}

export interface StoryActivity {
  readonly start_time: string
  readonly sport: string
  readonly duration_s: number | null
  readonly distance_m: number | null
  readonly elevation_gain_m: number | null
  readonly tss: number | null
  readonly hr_avg: number | null
  readonly hr_max: number | null
  readonly power_avg: number | null
  readonly pace_avg_s_per_km: number | null
  readonly calories: number | null
}

export interface StoryPoint {
  readonly latitude: number | null
  readonly longitude: number | null
  /**
   * Temps écoulé depuis le départ, en secondes. Sert à rattacher chaque point du
   * tracé à une discipline sur un multisport ; absent, le tracé reste monochrome.
   */
  readonly elapsed_s?: number | null
}

export interface StoryElevationPoint {
  readonly distance_m: number | null
  readonly elevation_m: number | null
}

export const STORY_SIZES: Record<StoryFormat, StorySize> = {
  story: { width: 1080, height: 1920 },
  square: { width: 1080, height: 1080 },
}

export const STORY_VIEW_LABELS: Record<StoryView, string> = {
  trace: 'Tracé + métriques',
  'stats-trace': 'Métriques + tracé',
  profil: 'Profil + métriques',
  stats: 'Métriques seules',
  disciplines: 'Par discipline',
  minimal: 'Tracé seul',
}

export const STORY_FORMAT_LABELS: Record<StoryFormat, string> = {
  story: 'Story 9:16',
  square: 'Carré 1:1',
}

export const STORY_BACKGROUND_LABELS: Record<StoryBackground, string> = {
  transparent: 'Transparent',
  dark: 'Sombre',
  gradient: 'Dégradé',
}

export const STORY_ACCENTS: readonly {
  readonly key: string
  readonly label: string
  readonly color: string
}[] = [
  { key: 'cyan', label: 'Cyan', color: '#22d3ee' },
  { key: 'white', label: 'Blanc', color: '#ffffff' },
  { key: 'orange', label: 'Orange', color: '#fb923c' },
  { key: 'violet', label: 'Violet', color: '#a78bfa' },
  { key: 'lime', label: 'Vert', color: '#a3e635' },
]

/** Points max envoyés au canvas : au-delà le rendu ne gagne plus rien en netteté. */
const MAX_RENDERED_POINTS = 900

/**
 * Points max sérialisés du serveur vers le composant client.
 *
 * Bien plus bas que `MAX_RENDERED_POINTS` : le calque ne dépasse pas 1080 px de large,
 * 300 points laissent déjà moins de 4 px entre deux sommets du tracé. Ce budget compte
 * double, car la page transmet déjà l'intégralité des samples à la carte MapLibre —
 * ces points-ci sont une seconde copie dans le payload RSC.
 */
export const STORY_TRANSFERRED_POINTS = 300

// Zone sûre : la UI Instagram (avatar en haut, barre de réponse en bas) mange les bords.
const SAFE_INSETS: Record<StoryFormat, { top: number; bottom: number; side: number }> = {
  story: { top: 260, bottom: 300, side: 88 },
  square: { top: 80, bottom: 88, side: 72 },
}

function isFiniteNumber(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function speedMsOf(activity: StoryActivity): number | null {
  if (isFiniteNumber(activity.pace_avg_s_per_km) && activity.pace_avg_s_per_km > 0) {
    return 1000 / activity.pace_avg_s_per_km
  }
  if (
    isFiniteNumber(activity.distance_m) &&
    isFiniteNumber(activity.duration_s) &&
    activity.duration_s > 0
  ) {
    return activity.distance_m / activity.duration_s
  }
  return null
}

function paceMetric(activity: StoryActivity, sport: Sport): StoryMetric | null {
  const speedMs = speedMsOf(activity)
  if (speedMs === null) return null
  const value = formatSpeedForSport(sport, speedMs)
  if (value === '—') return null
  return {
    key: 'pace',
    label: paceUnitForSport(sport) === 'km/h' ? 'Vitesse' : 'Allure',
    value,
  }
}

function integerMetric(
  key: string,
  label: string,
  value: number | null,
  suffix: string
): StoryMetric | null {
  if (!isFiniteNumber(value) || value <= 0) return null
  return { key, label, value: `${String(Math.round(value))}${suffix}` }
}

/**
 * Métriques candidates d'une activité, dans l'ordre d'importance pour un partage.
 * Les métriques absentes (pas de capteur, pas de GPS) sont simplement omises.
 */
export function buildStoryMetrics(activity: StoryActivity, sport: Sport): StoryMetric[] {
  const distance = isFiniteNumber(activity.distance_m) && activity.distance_m > 0
  const duration = isFiniteNumber(activity.duration_s) && activity.duration_s > 0
  const candidates: (StoryMetric | null)[] = [
    distance
      ? { key: 'distance', label: 'Distance', value: formatDistanceFromMeters(activity.distance_m) }
      : null,
    duration
      ? { key: 'duration', label: 'Durée', value: formatDuration(activity.duration_s) }
      : null,
    integerMetric('elevation', 'Dénivelé', activity.elevation_gain_m, ' m'),
    paceMetric(activity, sport),
    integerMetric('hr_avg', 'FC moyenne', activity.hr_avg, ' bpm'),
    integerMetric('hr_max', 'FC max', activity.hr_max, ' bpm'),
    integerMetric('power', 'Puissance', activity.power_avg, ' W'),
    integerMetric('tss', 'Charge', activity.tss, ' TSS'),
    integerMetric('calories', 'Calories', activity.calories, ' kcal'),
  ]
  return candidates.filter((metric): metric is StoryMetric => metric !== null)
}

/** Sélection par défaut : les premières métriques disponibles, dans la limite du gabarit. */
export function defaultMetricKeys(metrics: StoryMetric[], cap: number): string[] {
  return metrics.slice(0, cap).map((metric) => metric.key)
}

/**
 * Jour civil **local**, pas UTC : une sortie de fin de soirée serait datée de la veille
 * par `toISOString()`, en contradiction avec la date affichée sur le calque.
 */
function localDay(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${String(date.getFullYear())}-${month}-${day}`
}

/** Nom de fichier stable et lisible pour le PNG exporté. */
export function storyFileName(activity: StoryActivity, view: StoryView): string {
  const date = new Date(activity.start_time)
  const day = Number.isNaN(date.getTime()) ? 'activite' : localDay(date)
  const sport = activity.sport.toLowerCase().replaceAll(/[^a-z0-9]+/g, '-')
  return `garmin-coach-${day}-${sport}-${view}.png`
}

/** Élément empilé dans le sticker, du haut vers le bas. */
export type StoryBlockKind =
  | 'title'
  | 'route'
  | 'elevation'
  | 'metricsRow'
  | 'metricsStack'
  | 'segments'
  | 'brand'

export interface StoryBlock {
  readonly kind: StoryBlockKind
  readonly box: Box
}

export interface StoryLayout {
  readonly size: StorySize
  /** Facteur appliqué aux hauteurs ET aux tailles de police quand la pile déborde. */
  readonly scale: number
  readonly blocks: readonly StoryBlock[]
}

export function findStoryBlock(layout: StoryLayout, kind: StoryBlockKind): Box | null {
  return layout.blocks.find((block) => block.kind === kind)?.box ?? null
}

/**
 * Métriques affichables selon le gabarit : une ligne n'en tient que 3 côte à côte,
 * une pile de valeurs géantes en supporte 4 avant de déborder.
 */
export function metricsCapForView(view: StoryView): number {
  if (view === 'minimal') return 0
  // Sur le gabarit « par discipline », les métriques globales ne sont qu'un rappel
  // du total sous la pile : deux suffisent, au-delà elles concurrencent les lignes
  // de disciplines qui sont le sujet du calque.
  if (view === 'disciplines') return 2
  return view === 'stats' || view === 'stats-trace' ? 4 : 3
}

// Hauteurs de référence, en pixels d'un calque 1080 de large. La pile est ensuite
// réduite d'un facteur unique si elle ne rentre pas (format carré, 4 métriques…).
const BLOCK_GAP = 72
const TITLE_HEIGHT = 48
const BRAND_HEIGHT = 44
const ROUTE_HEIGHT_LARGE = 780
const ROUTE_HEIGHT_SMALL = 340
const ELEVATION_HEIGHT_LARGE = 440
const METRICS_ROW_HEIGHT = 150
const METRIC_LINE_HEIGHT = 142
const METRIC_LINE_GAP = 52
const SEGMENT_LINE_HEIGHT = 118
const SEGMENT_LINE_GAP = 40

function metricsStackHeight(count: number): number {
  return count * METRIC_LINE_HEIGHT + (count - 1) * METRIC_LINE_GAP
}

/** Hauteur de la pile « une ligne par discipline » du gabarit multisport. */
export function segmentsBlockHeight(count: number): number {
  if (count <= 0) return 0
  return count * SEGMENT_LINE_HEIGHT + (count - 1) * SEGMENT_LINE_GAP
}

interface StackItem {
  readonly kind: StoryBlockKind
  readonly height: number
}

function stackItems(view: StoryView, metricCount: number, segmentCount: number): StackItem[] {
  if (view === 'disciplines') {
    return [
      { kind: 'segments', height: segmentsBlockHeight(segmentCount) },
      { kind: 'metricsRow', height: METRICS_ROW_HEIGHT },
    ]
  }
  if (view === 'stats-trace') {
    return [
      { kind: 'metricsStack', height: metricsStackHeight(metricCount) },
      { kind: 'route', height: ROUTE_HEIGHT_SMALL },
    ]
  }
  if (view === 'stats') {
    return [{ kind: 'metricsStack', height: metricsStackHeight(metricCount) }]
  }
  const visual: StackItem =
    view === 'profil'
      ? { kind: 'elevation', height: ELEVATION_HEIGHT_LARGE }
      : { kind: 'route', height: ROUTE_HEIGHT_LARGE }
  return [visual, { kind: 'metricsRow', height: METRICS_ROW_HEIGHT }]
}

interface StoryLayoutOptions {
  readonly showTitle?: boolean
  readonly showBrand?: boolean
  /** Nombre de lignes de disciplines à réserver (gabarit `disciplines`). */
  readonly segmentCount?: number
}

/**
 * Compose le sticker : une pile de blocs centrée horizontalement et verticalement
 * dans la zone sûre, à la manière des calques de partage d'activité.
 *
 * Le contenu ne remplit volontairement pas toute la hauteur — un sticker compact se
 * déplace et se redimensionne bien dans l'éditeur de story.
 */
export function computeStoryLayout(
  view: StoryView,
  format: StoryFormat,
  metricCount: number,
  options: StoryLayoutOptions = {}
): StoryLayout {
  const size = STORY_SIZES[format]
  const insets = SAFE_INSETS[format]
  const left = insets.side
  const width = size.width - insets.side * 2
  const top = insets.top
  const available = size.height - insets.bottom - top

  if (view === 'minimal') {
    return {
      size,
      scale: 1,
      blocks: [{ kind: 'route', box: { x: left, y: top, width, height: available } }],
    }
  }

  const shownMetrics = Math.min(metricCount, metricsCapForView(view))
  const segmentCount = options.segmentCount ?? 0
  const items: StackItem[] = [
    ...(options.showTitle === false ? [] : [{ kind: 'title' as const, height: TITLE_HEIGHT }]),
    ...stackItems(view, shownMetrics, segmentCount).filter(
      (item) =>
        item.height > 0 &&
        (shownMetrics > 0 || (item.kind !== 'metricsRow' && item.kind !== 'metricsStack'))
    ),
    ...(options.showBrand === false ? [] : [{ kind: 'brand' as const, height: BRAND_HEIGHT }]),
  ]
  if (items.length === 0) return { size, scale: 1, blocks: [] }

  const naturalHeight =
    items.reduce((total, item) => total + item.height, 0) + BLOCK_GAP * (items.length - 1)
  const scale = Math.min(1, available / naturalHeight)
  const gap = BLOCK_GAP * scale

  let y = top + (available - naturalHeight * scale) / 2
  const blocks: StoryBlock[] = []
  for (const item of items) {
    const height = item.height * scale
    blocks.push({ kind: item.kind, box: { x: left, y, width, height } })
    y += height + gap
  }

  return { size, scale, blocks }
}

export interface ProjectedRoute {
  /** Points projetés en coordonnées canvas, déjà centrés dans la boîte. */
  readonly points: readonly (readonly [number, number])[]
  /**
   * Temps écoulé de chaque point, même longueur et même ordre que `points`
   * (`NaN` quand la donnée manque). Permet de découper le tracé par discipline
   * après projection, sans refaire le filtrage ni le sous-échantillonnage.
   */
  readonly elapsed: readonly number[]
}

function sampleEvenly<T>(items: readonly T[], max: number): T[] {
  if (items.length <= max) return [...items]
  const step = (items.length - 1) / (max - 1)
  const out: T[] = []
  for (let i = 0; i < max; i++) {
    const item = items[Math.round(i * step)]
    if (item !== undefined) out.push(item)
  }
  return out
}

/**
 * Projette une trace GPS dans une boîte canvas.
 *
 * Projection équirectangulaire corrigée par `cos(latitude moyenne)` : à l'échelle
 * d'une sortie, l'erreur est négligeable et le rapport d'aspect reste réaliste
 * (une boucle carrée sur le terrain reste carrée sur l'image).
 */
export function projectRoute(points: readonly StoryPoint[], box: Box): ProjectedRoute | null {
  const coords: [number, number, number][] = []
  for (const point of points) {
    if (isFiniteNumber(point.latitude) && isFiniteNumber(point.longitude)) {
      coords.push([point.longitude, point.latitude, point.elapsed_s ?? Number.NaN])
    }
  }
  if (coords.length < 2) return null

  const sampled = sampleEvenly(coords, MAX_RENDERED_POINTS)
  const lats = sampled.map(([, lat]) => lat)
  const meanLat = lats.reduce((acc, lat) => acc + lat, 0) / lats.length
  const cosLat = Math.max(0.1, Math.cos((meanLat * Math.PI) / 180))

  const planar = sampled.map(([lng, lat]) => [lng * cosLat, lat] as [number, number])
  const elapsed = sampled.map(([, , seconds]) => seconds)
  const xs = planar.map(([x]) => x)
  const ys = planar.map(([, y]) => y)
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  const spanX = maxX - minX
  const spanY = maxY - minY
  if (spanX === 0 && spanY === 0) return null

  // Échelle uniforme sur l'axe le plus contraignant, puis centrage dans la boîte.
  const scale = Math.min(
    spanX === 0 ? Number.POSITIVE_INFINITY : box.width / spanX,
    spanY === 0 ? Number.POSITIVE_INFINITY : box.height / spanY
  )
  const drawnWidth = spanX * scale
  const drawnHeight = spanY * scale
  const offsetX = box.x + (box.width - drawnWidth) / 2
  const offsetY = box.y + (box.height - drawnHeight) / 2

  const projected = planar.map(([x, y]) => {
    const px = offsetX + (x - minX) * scale
    // Le canvas a l'axe Y vers le bas : le nord doit rester en haut.
    const py = offsetY + drawnHeight - (y - minY) * scale
    return [px, py] as const
  })

  return { points: projected, elapsed }
}

export interface StorySampleInput {
  readonly latitude: number | null
  readonly longitude: number | null
  readonly distance_m: number | null
  readonly elevation_m: number | null
  readonly elapsed_s?: number | null
}

export interface StorySampleSets {
  readonly route: StoryPoint[]
  readonly elevation: StoryElevationPoint[]
}

const COORD_PRECISION = 100_000

/**
 * Réduit les samples d'une activité au strict nécessaire pour le calque, côté serveur.
 *
 * Le budget est volontairement serré (`STORY_TRANSFERRED_POINTS`) : ces points partent
 * dans le payload RSC en plus des samples complets déjà transmis à la carte, et 300
 * suffisent à un tracé de 1080 px de large.
 */
export function compactSamplesForStory(samples: readonly StorySampleInput[]): StorySampleSets {
  const route = sampleEvenly(
    samples.filter((s) => isFiniteNumber(s.latitude) && isFiniteNumber(s.longitude)),
    STORY_TRANSFERRED_POINTS
  ).map((s) => ({
    latitude: Math.round((s.latitude ?? 0) * COORD_PRECISION) / COORD_PRECISION,
    longitude: Math.round((s.longitude ?? 0) * COORD_PRECISION) / COORD_PRECISION,
    // Une seconde près suffit à rattacher un point du tracé à sa discipline.
    elapsed_s: isFiniteNumber(s.elapsed_s) ? Math.round(s.elapsed_s) : null,
  }))

  const elevation = sampleEvenly(
    samples.filter((s) => isFiniteNumber(s.elevation_m)),
    STORY_TRANSFERRED_POINTS
  ).map((s) => ({
    distance_m: isFiniteNumber(s.distance_m) ? Math.round(s.distance_m) : null,
    elevation_m: Math.round(s.elevation_m ?? 0),
  }))

  return { route, elevation }
}

export interface ElevationProfile {
  readonly points: readonly (readonly [number, number])[]
  readonly baselineY: number
  readonly minElevation: number
  readonly maxElevation: number
  /** Point le plus haut du profil, pour annoter l'altitude maximale. */
  readonly peak: readonly [number, number]
}

/**
 * Construit le profil altimétrique (silhouette) dans une boîte canvas.
 * L'axe X suit la distance parcourue quand elle est disponible, sinon l'index.
 */
export function buildElevationProfile(
  samples: readonly StoryElevationPoint[],
  box: Box
): ElevationProfile | null {
  const usable = samples.filter(
    (sample): sample is { distance_m: number | null; elevation_m: number } =>
      isFiniteNumber(sample.elevation_m)
  )
  if (usable.length < 2) return null

  const sampled = sampleEvenly(usable, MAX_RENDERED_POINTS)
  const elevations = sampled.map((sample) => sample.elevation_m)
  const minElevation = Math.min(...elevations)
  const maxElevation = Math.max(...elevations)
  const span = maxElevation - minElevation
  const hasDistance = sampled.every((sample) => isFiniteNumber(sample.distance_m))
  const lastDistance = hasDistance ? (sampled.at(-1)?.distance_m ?? 0) : 0
  const distanceSpan = hasDistance && lastDistance > 0 ? lastDistance : 0

  const baselineY = box.y + box.height
  let peak: readonly [number, number] = [box.x, baselineY]

  const points = sampled.map((sample, index) => {
    const ratioX =
      distanceSpan > 0
        ? Math.min(1, Math.max(0, (sample.distance_m ?? 0) / distanceSpan))
        : index / (sampled.length - 1)
    const ratioY = span > 0 ? (sample.elevation_m - minElevation) / span : 0.5
    const x = box.x + ratioX * box.width
    const y = baselineY - ratioY * box.height
    if (sample.elevation_m === maxElevation) peak = [x, y]
    return [x, y] as const
  })

  return { points, baselineY, minElevation, maxElevation, peak }
}
