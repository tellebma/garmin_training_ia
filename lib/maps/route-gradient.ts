import type { ActivitySample } from '@/lib/coach/activity-analysis'

export type RouteMetric = 'hr' | 'speed' | 'elevation'

export const METRIC_LABELS: Record<RouteMetric, string> = {
  hr: 'FC',
  speed: 'Vitesse',
  elevation: 'Altitude',
}

const METRIC_FIELD: Record<RouteMetric, keyof ActivitySample> = {
  hr: 'heart_rate_bpm',
  speed: 'speed_m_s',
  elevation: 'elevation_m',
}

const clamp01 = (t: number) => Math.min(1, Math.max(0, t))

export function metricColor(t: number): string {
  // Blue (cold/slow/low) -> red (hot/fast/high) through green/yellow.
  const hue = 220 * (1 - clamp01(t))
  return `hsl(${String(Math.round(hue))}, 80%, 55%)`
}

interface GpsPoint {
  lng: number
  lat: number
  value: number | null
}

function gpsPoints(samples: ActivitySample[], field: keyof ActivitySample): GpsPoint[] {
  return samples
    .filter(
      (s): s is ActivitySample & { latitude: number; longitude: number } =>
        typeof s.latitude === 'number' && typeof s.longitude === 'number'
    )
    .map((s) => {
      const value = s[field]
      return {
        lng: s.longitude,
        lat: s.latitude,
        value: typeof value === 'number' ? value : null,
      }
    })
}

export function availableMetrics(samples: ActivitySample[]): RouteMetric[] {
  return (Object.keys(METRIC_FIELD) as RouteMetric[]).filter((metric) => {
    const count = gpsPoints(samples, METRIC_FIELD[metric]).filter((p) => p.value !== null).length
    return count >= 2
  })
}

function fillValues(points: GpsPoint[]): number[] | null {
  if (points.every((p) => p.value === null)) return null
  const filled: number[] = []
  let last: number | null = null
  for (const p of points) {
    if (p.value !== null) last = p.value
    filled.push(last ?? Number.NaN)
  }
  // Back-fill the leading NaNs with the first known value.
  const firstKnown = filled.find((v) => !Number.isNaN(v)) ?? 0
  return filled.map((v) => (Number.isNaN(v) ? firstKnown : v))
}

function cumulativeFractions(points: GpsPoint[]): number[] | null {
  if (points.length === 0) return null
  const totalLat = points.reduce((acc: number, p) => acc + p.lat, 0)
  const meanLat = totalLat / points.length
  const cosLat = Math.cos((meanLat * Math.PI) / 180)
  const distances: number[] = [0]
  for (let i = 1; i < points.length; i++) {
    const current = points[i]
    const previous = points[i - 1]
    if (current && previous) {
      const dx = (current.lng - previous.lng) * cosLat
      const dy = current.lat - previous.lat
      const prevDistance = distances[i - 1]
      if (prevDistance !== undefined) {
        distances.push(prevDistance + Math.hypot(dx, dy))
      }
    }
  }
  const total = distances.at(-1)
  if (!total || total <= 0) return null
  return distances.map((d) => d / total)
}

export function buildMetricGradient(
  samples: ActivitySample[],
  metric: RouteMetric
): (string | number)[] | null {
  const points = gpsPoints(samples, METRIC_FIELD[metric])
  if (points.length < 2) return null

  const values = fillValues(points)
  const fractions = cumulativeFractions(points)
  if (!values || !fractions) return null

  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min

  const stops: (string | number)[] = []
  let lastStop = -1
  fractions.forEach((frac, i) => {
    // Stops must be strictly increasing; skip duplicates from coincident points.
    if (frac <= lastStop) return
    lastStop = frac
    const value = values[i]
    if (value !== undefined) {
      const normalized = span > 0 ? (value - min) / span : 0.5
      stops.push(frac, metricColor(normalized))
    }
  })

  if (stops.length < 4) return null
  // MapLibre interpolate expression: ['interpolate', ['linear'], ['line-progress'], stop0, color0, stop1, color1, ...]
  return ['interpolate', ['linear'], ['line-progress'], ...stops] as (string | number)[]
}
