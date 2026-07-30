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
 * - `trace`   : tracé GPS + bandeau de métriques
 * - `profil`  : profil altimétrique + bandeau de métriques
 * - `stats`   : métriques seules en gros (activités sans GPS : home-trainer, piscine…)
 * - `minimal` : tracé seul, sans texte (calque à superposer librement)
 */
export type StoryView = 'trace' | 'profil' | 'stats' | 'minimal'

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
  profil: 'Profil + métriques',
  stats: 'Métriques seules',
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

/** Nombre maximum de métriques affichées sur un calque (grille 2 colonnes). */
export const MAX_STORY_METRICS = 6

/** Points max envoyés au canvas : au-delà le rendu ne gagne plus rien en netteté. */
const MAX_RENDERED_POINTS = 900

interface FormatStyle {
  /** Zone sûre : la UI Instagram (avatar en haut, barre de réponse en bas) mange les bords. */
  readonly top: number
  readonly bottom: number
  readonly side: number
  readonly headerHeight: number
  readonly brandHeight: number
  readonly gap: number
  readonly rowHeight: number
  readonly rowHeightLarge: number
  readonly maxColumns: number
}

const FORMAT_STYLES: Record<StoryFormat, FormatStyle> = {
  story: {
    top: 260,
    bottom: 300,
    side: 88,
    headerHeight: 150,
    brandHeight: 56,
    gap: 56,
    rowHeight: 156,
    rowHeightLarge: 214,
    maxColumns: 2,
  },
  square: {
    top: 80,
    bottom: 88,
    side: 72,
    headerHeight: 124,
    brandHeight: 50,
    gap: 36,
    rowHeight: 146,
    rowHeightLarge: 168,
    maxColumns: 3,
  },
}

/** Hauteur minimale sous laquelle un visuel (tracé, profil) n'est plus lisible. */
const MIN_VISUAL_HEIGHT = 200

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

/** Sélection par défaut : les `MAX_STORY_METRICS` premières métriques disponibles. */
export function defaultMetricKeys(metrics: StoryMetric[]): string[] {
  return metrics.slice(0, MAX_STORY_METRICS).map((metric) => metric.key)
}

/** Nom de fichier stable et lisible pour le PNG exporté. */
export function storyFileName(activity: StoryActivity, view: StoryView): string {
  const date = new Date(activity.start_time)
  const day = Number.isNaN(date.getTime()) ? 'activite' : date.toISOString().slice(0, 10)
  const sport = activity.sport.toLowerCase().replaceAll(/[^a-z0-9]+/g, '-')
  return `garmin-coach-${day}-${sport}-${view}.png`
}

export interface StoryLayout {
  readonly size: StorySize
  readonly header: Box | null
  readonly visual: Box | null
  readonly metrics: Box | null
  readonly brand: Box | null
  readonly columns: number
  readonly large: boolean
}

function metricRows(count: number, columns: number): number {
  return count === 0 ? 0 : Math.ceil(count / columns)
}

/**
 * Colonnes de la grille : la plus large division exacte du nombre de métriques,
 * pour éviter une dernière ligne dépareillée (4 métriques → 2×2, pas 3+1).
 */
function metricColumns(count: number, maxColumns: number): number {
  if (count <= 1) return 1
  if (count <= maxColumns) return count
  for (let columns = maxColumns; columns >= 2; columns--) {
    if (count % columns === 0) return columns
  }
  return maxColumns
}

/**
 * Découpe verticale du calque : en-tête, visuel (tracé ou profil), grille de
 * métriques, signature. Le visuel absorbe tout l'espace restant.
 */
export function computeStoryLayout(
  view: StoryView,
  format: StoryFormat,
  metricCount: number
): StoryLayout {
  const size = STORY_SIZES[format]
  const style = FORMAT_STYLES[format]
  const left = style.side
  const width = size.width - style.side * 2
  const top = style.top
  const bottom = size.height - style.bottom

  if (view === 'minimal') {
    return {
      size,
      header: null,
      visual: { x: left, y: top, width, height: bottom - top },
      metrics: null,
      brand: null,
      columns: 0,
      large: false,
    }
  }

  const large = view === 'stats'
  // En vue « métriques seules » les valeurs sont énormes : au-delà de 2 colonnes
  // l'ajustement automatique les rapetisserait plus que les libellés.
  const columns = metricColumns(
    metricCount,
    large ? Math.min(2, style.maxColumns) : style.maxColumns
  )
  const rows = metricRows(metricCount, columns)
  const rowHeight = large ? style.rowHeightLarge : style.rowHeight
  const metricsHeight = rows * rowHeight

  const brand: Box = { x: left, y: bottom - style.brandHeight, width, height: style.brandHeight }
  const header: Box = { x: left, y: top, width, height: style.headerHeight }

  const metricsBottom = brand.y - style.gap
  const metrics: Box | null =
    rows === 0 ? null : { x: left, y: metricsBottom - metricsHeight, width, height: metricsHeight }

  if (large) {
    // Pas de visuel : la grille est centrée entre l'en-tête et la signature.
    if (!metrics) return { size, header, visual: null, metrics: null, brand, columns, large }
    const availableTop = header.y + header.height + style.gap
    const centered = availableTop + (metricsBottom - availableTop - metricsHeight) / 2
    return {
      size,
      header,
      visual: null,
      metrics: { ...metrics, y: Math.max(availableTop, centered) },
      brand,
      columns,
      large,
    }
  }

  const visualTop = header.y + header.height + style.gap
  const visualBottom = (metrics?.y ?? metricsBottom) - style.gap
  const visual: Box | null =
    visualBottom - visualTop >= MIN_VISUAL_HEIGHT
      ? { x: left, y: visualTop, width, height: visualBottom - visualTop }
      : null

  return { size, header, visual, metrics, brand, columns, large }
}

export interface ProjectedRoute {
  /** Points projetés en coordonnées canvas, déjà centrés dans la boîte. */
  readonly points: readonly (readonly [number, number])[]
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
  const coords: [number, number][] = []
  for (const point of points) {
    if (isFiniteNumber(point.latitude) && isFiniteNumber(point.longitude)) {
      coords.push([point.longitude, point.latitude])
    }
  }
  if (coords.length < 2) return null

  const sampled = sampleEvenly(coords, MAX_RENDERED_POINTS)
  const lats = sampled.map(([, lat]) => lat)
  const meanLat = lats.reduce((acc, lat) => acc + lat, 0) / lats.length
  const cosLat = Math.max(0.1, Math.cos((meanLat * Math.PI) / 180))

  const planar = sampled.map(([lng, lat]) => [lng * cosLat, lat] as [number, number])
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

  return { points: projected }
}

export interface StorySampleInput {
  readonly latitude: number | null
  readonly longitude: number | null
  readonly distance_m: number | null
  readonly elevation_m: number | null
}

export interface StorySampleSets {
  readonly route: StoryPoint[]
  readonly elevation: StoryElevationPoint[]
}

const COORD_PRECISION = 100_000

/**
 * Réduit les samples d'une activité au strict nécessaire pour le calque, côté
 * serveur : le composant client est sérialisé dans le payload RSC, inutile d'y
 * pousser plusieurs milliers de points que le rendu n'exploite pas.
 */
export function compactSamplesForStory(samples: readonly StorySampleInput[]): StorySampleSets {
  const route = sampleEvenly(
    samples.filter((s) => isFiniteNumber(s.latitude) && isFiniteNumber(s.longitude)),
    MAX_RENDERED_POINTS
  ).map((s) => ({
    latitude: Math.round((s.latitude ?? 0) * COORD_PRECISION) / COORD_PRECISION,
    longitude: Math.round((s.longitude ?? 0) * COORD_PRECISION) / COORD_PRECISION,
  }))

  const elevation = sampleEvenly(
    samples.filter((s) => isFiniteNumber(s.elevation_m)),
    MAX_RENDERED_POINTS
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
