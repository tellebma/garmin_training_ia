/**
 * Aggregates every recorded GPS route into a frequency-weighted line network:
 * how many distinct activities travelled each stretch of road.
 *
 * Why not a plain point heatmap (the previous implementation):
 *  - `route_polyline` is a *downsampled* trace (~64 points per activity), so the
 *    on-screen point density encodes the sampling step (≈90 m for a run, ≈540 m
 *    for a ride), not how often the athlete went there;
 *  - a kernel heatmap sums neighbouring points, and a single pass already puts
 *    enough points inside the kernel radius to saturate the ramp — hence "tout
 *    apparaît rouge" when zoomed out.
 *
 * The fix is an explicit spatial aggregation:
 *  1. resample each route at a fixed *ground* spacing, so cell membership no
 *     longer depends on how the trace was downsampled;
 *  2. count the number of *distinct activities* per grid cell;
 *  3. emit line segments carrying that count, so the renderer can encode it with
 *     colour AND width instead of relying on overdraw.
 */
import { isLngLat } from './geo'

export type LngLat = [number, number]

export interface RouteFrequencyFeature {
  type: 'Feature'
  geometry: { type: 'LineString'; coordinates: LngLat[] }
  properties: { passages: number }
}

export interface RouteFrequencyCollection {
  type: 'FeatureCollection'
  features: RouteFrequencyFeature[]
}

export interface RouteFrequencyResult {
  collection: RouteFrequencyCollection
  /** Ascending lower bounds of the frequency classes. Always starts at 1. */
  breaks: number[]
  maxPassages: number
  bounds: [LngLat, LngLat] | null
}

/** Grid cell side, in metres. Coarse enough to absorb downsampling drift. */
const CELL_SIZE_M = 300
/** Resampling step, in metres. Must stay well below CELL_SIZE_M. */
const SAMPLE_SPACING_M = 100
/** Safety valve against a pathological polyline (one 500 km straight segment). */
const MAX_POINTS_PER_SEGMENT = 2000

const METERS_PER_DEG = 111_320

/**
 * Sequential single-hue (blue) ramp, dark -> light: tuned for a dark basemap,
 * where "rarely travelled" must recede toward the background and "very often"
 * must pop. Paired with an increasing width so the encoding is never colour-alone.
 */
export const FREQUENCY_COLORS = ['#1c5cab', '#2a78d6', '#5598e7', '#9ec5f4', '#cde2fb'] as const
/** Line width per class at low zoom (whole-region view) and at high zoom. */
export const FREQUENCY_WIDTHS_LOW = [0.8, 1.2, 1.8, 2.6, 3.6] as const
export const FREQUENCY_WIDTHS_HIGH = [1.6, 2.6, 4, 6, 8.5] as const

function parseRoutes(polylines: readonly unknown[]): LngLat[][] {
  const routes: LngLat[][] = []
  for (const polyline of polylines) {
    if (!Array.isArray(polyline)) continue
    const points: LngLat[] = []
    for (const point of polyline) {
      if (isLngLat(point)) points.push([point[0], point[1]])
    }
    if (points.length >= 2) routes.push(points)
  }
  return routes
}

function meanLatitude(routes: readonly LngLat[][]): number {
  let sum = 0
  let count = 0
  for (const route of routes) {
    for (const [, lat] of route) {
      sum += lat
      count += 1
    }
  }
  return count === 0 ? 0 : sum / count
}

/**
 * Resamples a polyline so that no two consecutive points are further apart than
 * `spacingM` on the ground, while keeping the original vertices (shape fidelity).
 */
export function resamplePolyline(
  points: readonly LngLat[],
  spacingM: number,
  cosLat: number
): LngLat[] {
  const first = points[0]
  if (!first || points.length < 2) return first ? [first] : []

  const out: LngLat[] = [first]
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1]
    const b = points[i]
    if (!a || !b) continue
    const dx = (b[0] - a[0]) * cosLat * METERS_PER_DEG
    const dy = (b[1] - a[1]) * METERS_PER_DEG
    const length = Math.hypot(dx, dy)
    const steps = Math.min(Math.max(1, Math.ceil(length / spacingM)), MAX_POINTS_PER_SEGMENT)
    for (let k = 1; k <= steps; k++) {
      const t = k / steps
      out.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t])
    }
  }
  return out
}

function cellKey(point: LngLat, cosLat: number): string {
  const x = Math.floor((point[0] * cosLat * METERS_PER_DEG) / CELL_SIZE_M)
  const y = Math.floor((point[1] * METERS_PER_DEG) / CELL_SIZE_M)
  return `${String(x)}:${String(y)}`
}

/**
 * Frequency-class thresholds calibrated on the *observed* distribution rather
 * than on a fixed 0..max linear scale: passage counts are heavily right-skewed
 * (most stretches ridden once, a couple of hot roads ridden 30+ times), so a
 * linear ramp would collapse everything into the first class.
 */
export function computeBreaks(weights: readonly number[]): number[] {
  const repeated = weights.filter((v) => v >= 2).sort((a, b) => a - b)
  if (repeated.length === 0) return [1]

  const quantile = (p: number): number => {
    const index = Math.min(repeated.length - 1, Math.floor(p * repeated.length))
    return repeated[index] ?? 2
  }

  const breaks: number[] = [1]
  for (const candidate of [2, quantile(0.5), quantile(0.8), quantile(0.95)]) {
    const last = breaks[breaks.length - 1] ?? 1
    if (candidate > last) breaks.push(candidate)
  }
  return breaks
}

/** Human label for each class, e.g. ["1", "2", "3-5", "6-11", "12+"]. */
export function frequencyLabels(breaks: readonly number[], maxPassages: number): string[] {
  return breaks.map((lower, i) => {
    const next = breaks[i + 1]
    if (next === undefined) return lower >= maxPassages ? String(lower) : `${String(lower)}+`
    const upper = next - 1
    return upper <= lower ? String(lower) : `${String(lower)}-${String(upper)}`
  })
}

interface PendingSegment {
  passages: number
  coordinates: LngLat[]
}

function pushMerged(features: RouteFrequencyFeature[], pending: PendingSegment | null): void {
  if (!pending || pending.coordinates.length < 2) return
  features.push({
    type: 'Feature',
    geometry: { type: 'LineString', coordinates: pending.coordinates },
    properties: { passages: pending.passages },
  })
}

/**
 * Extends the stretch being accumulated when the weight is unchanged, otherwise
 * flushes it and starts a new one — this is what merges thousands of 100 m
 * fragments back into a handful of readable lines.
 */
function appendStretch(
  features: RouteFrequencyFeature[],
  pending: PendingSegment | null,
  passages: number,
  a: LngLat,
  b: LngLat
): PendingSegment {
  if (pending?.passages === passages) {
    pending.coordinates.push(b)
    return pending
  }
  pushMerged(features, pending)
  return { passages, coordinates: [a, b] }
}

function boundsOf(routes: readonly LngLat[][]): [LngLat, LngLat] | null {
  let minLng = Infinity
  let minLat = Infinity
  let maxLng = -Infinity
  let maxLat = -Infinity
  for (const route of routes) {
    for (const [lng, lat] of route) {
      minLng = Math.min(minLng, lng)
      maxLng = Math.max(maxLng, lng)
      minLat = Math.min(minLat, lat)
      maxLat = Math.max(maxLat, lat)
    }
  }
  if (!Number.isFinite(minLng)) return null
  return [
    [minLng, minLat],
    [maxLng, maxLat],
  ]
}

const EMPTY_RESULT: RouteFrequencyResult = {
  collection: { type: 'FeatureCollection', features: [] },
  breaks: [1],
  maxPassages: 0,
  bounds: null,
}

export function buildRouteFrequencyGeoJson(polylines: readonly unknown[]): RouteFrequencyResult {
  const routes = parseRoutes(polylines)
  if (routes.length === 0) return EMPTY_RESULT

  const cosLat = Math.cos((meanLatitude(routes) * Math.PI) / 180) || 1
  const dense = routes.map((route) => resamplePolyline(route, SAMPLE_SPACING_M, cosLat))

  // Pass 1 — how many distinct activities touched each grid cell.
  const cellActivities = new Map<string, Set<number>>()
  dense.forEach((route, routeIndex) => {
    for (const point of route) {
      const key = cellKey(point, cosLat)
      const set = cellActivities.get(key)
      if (set) set.add(routeIndex)
      else cellActivities.set(key, new Set([routeIndex]))
    }
  })
  const passagesAt = (point: LngLat): number =>
    cellActivities.get(cellKey(point, cosLat))?.size ?? 1

  // Pass 2 — weight each stretch, merging consecutive stretches of equal weight.
  const features: RouteFrequencyFeature[] = []
  const weights: number[] = []
  let maxPassages = 0
  for (const route of dense) {
    let pending: PendingSegment | null = null
    for (let i = 1; i < route.length; i++) {
      const a = route[i - 1]
      const b = route[i]
      if (!a || !b) continue
      // `min` keeps a cold stretch from inheriting the heat of the cell it enters.
      const passages = Math.min(passagesAt(a), passagesAt(b))
      weights.push(passages)
      maxPassages = Math.max(maxPassages, passages)
      pending = appendStretch(features, pending, passages, a, b)
    }
    pushMerged(features, pending)
  }

  // Ascending sort so the busiest roads are painted last (and on top).
  features.sort((x, y) => x.properties.passages - y.properties.passages)

  return {
    collection: { type: 'FeatureCollection', features },
    breaks: computeBreaks(weights),
    maxPassages,
    bounds: boundsOf(routes),
  }
}
