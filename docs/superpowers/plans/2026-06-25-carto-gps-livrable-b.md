# Cartographie GPS — Livrable B (rendu enrichi) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrichir le rendu des traces GPS déjà collectées : trace colorée par métrique (FC / vitesse / altitude) sur le détail activité, vignette SVG de trace dans la liste historique, et heatmap globale « Où je m'entraîne » sur la page stats.

**Architecture:** Le Livrable A a déjà câblé le pipeline data (colonnes `activity_samples.latitude/longitude`, `activities.route_polyline`, extraction worker, backfill) et une carte de trace cyan unie (`ActivityRouteMap`). Le Livrable B ne touche **pas** au worker ni au schéma : il ne fait que consommer les données existantes côté frontend. Trois rendus purs s'appuient sur des utils testables : un gradient `line-gradient` MapLibre (détail), un `<path>` SVG sans tuiles (vignette), une couche `heatmap` MapLibre (stats).

**Tech Stack:** Next.js 15 / TypeScript strict, `maplibre-gl` ^5.24 (déjà installé), Vitest, `@testing-library/react`. Aucune dépendance nouvelle.

## Global Constraints

- Spec de référence : `docs/superpowers/specs/2026-06-24-gps-routes-maps-design.md` (sections §3 vignettes/heatmap/trace colorée, livrable B).
- **Aucune modification worker, schéma ou migration** : le Livrable B est frontend-only.
- Composants MapLibre **client-only** : `dynamic(() => import(...), { ssr: false })`, jamais de SSR WebGL.
- Vignette historique = **SVG pur, zéro requête réseau** (pas de tuiles, pas d'instance WebGL par ligne).
- Fond de carte = CARTO dark : `https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json` (réutiliser la constante du Livrable A, sans clé API).
- Données déjà downsamplées à ≤ 64 points (`route_polyline`) — ne pas re-downsampler côté front.
- `route_polyline` est lu depuis Supabase comme `unknown` (jsonb) → **toujours parser défensivement** avant usage.
- Accessibilité : tout canvas MapLibre reste `aria-hidden="true"` avec une alternative `sr-only` (même pattern que `ActivityRouteMap` existant).
- Conventions de commit : Conventional Commits, body ≤ 100 chars.
- Quality gates frontend : `pnpm test && pnpm lint && pnpm typecheck && rm -rf .next && pnpm build`. Coverage Sonar 97 % à préserver (chaque util pur est testé).
- Branche de travail : `feat/carto-gps-livrable-b` (depuis `main`).
- Immutabilité : créer de nouveaux objets, pas de mutation (spread/map/filter) — règle projet.

---

## File Structure

**Utils purs (testés à fond)**
- `lib/maps/route-polyline.ts` — *create* — `parseRoutePolyline()` (jsonb → `[lng,lat][]`) + `routeToSvgPath()` (projection vignette).
- `lib/maps/route-gradient.ts` — *create* — `metricColor()`, `availableMetrics()`, `buildMetricGradient()` (expression `line-gradient`).
- `lib/maps/heatmap-geojson.ts` — *create* — `buildHeatmapFeatureCollection()` (points agrégés) + `flattenRoutePoints()`.

**Composants carte**
- `app/(app)/_components/maps/activity-route-map.tsx` — *modify* — trace colorée par métrique + toggle.
- `app/(app)/_components/maps/route-thumbnail.tsx` — *create* — vignette SVG (server-renderable).
- `app/(app)/_components/maps/routes-heatmap.tsx` — *create* — couche heatmap MapLibre (client).
- `app/(app)/_components/maps/routes-heatmap-lazy.tsx` — *create* — wrapper `dynamic` ssr:false.

**Intégrations pages**
- `lib/dashboard/types.ts` — *modify* — `ActivityRowDto.route_polyline?: unknown`.
- `app/(app)/_components/activity-row.tsx` — *modify* — rend la vignette `RouteThumbnail`.
- `app/(app)/history/page.tsx` — *modify* — ajoute `route_polyline` au `select`.
- `app/(app)/stats/page.tsx` — *modify* — requête `route_polyline` + section heatmap.

**Tests**
- `tests/unit/maps/route-polyline.test.ts` — *create*
- `tests/unit/maps/route-gradient.test.ts` — *create*
- `tests/unit/maps/heatmap-geojson.test.ts` — *create*
- `tests/unit/components/route-thumbnail.test.tsx` — *create*
- `tests/unit/components/activity-route-map.test.tsx` — *modify* — toggle métrique
- `tests/unit/components/routes-heatmap.test.tsx` — *create*

---

## Task 1: Util `route-polyline` — parse jsonb + projection SVG

**Files:**
- Create: `lib/maps/route-polyline.ts`
- Test: `tests/unit/maps/route-polyline.test.ts`

**Interfaces:**
- Produces:
  - `type LngLat = [number, number]`
  - `parseRoutePolyline(value: unknown): LngLat[] | null` — valide un jsonb `[[lng,lat],...]`, retourne `null` si < 2 paires valides.
  - `routeToSvgPath(points: LngLat[], opts: { width: number; height: number; padding: number }): string | null` — attribut `d` d'un `<path>`, aspect-ratio préservé (correction `cos(lat)`), y inversé (lat haut = y bas). `null` si < 2 points.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/maps/route-polyline.test.ts` :

```ts
import { describe, expect, it } from 'vitest'
import { parseRoutePolyline, routeToSvgPath } from '@/lib/maps/route-polyline'

describe('parseRoutePolyline', () => {
  it('parses a valid lng/lat array', () => {
    expect(
      parseRoutePolyline([
        [4.1, 45.1],
        [4.2, 45.2],
      ])
    ).toEqual([
      [4.1, 45.1],
      [4.2, 45.2],
    ])
  })

  it('drops malformed pairs and returns null below two points', () => {
    expect(parseRoutePolyline([[4.1, 45.1], [4.2], ['a', 'b']])).toBeNull()
    expect(parseRoutePolyline(null)).toBeNull()
    expect(parseRoutePolyline('nope')).toBeNull()
    expect(parseRoutePolyline([[4.1, 45.1]])).toBeNull()
  })

  it('rejects out-of-range coordinates', () => {
    expect(
      parseRoutePolyline([
        [200, 45.1],
        [4.2, 45.2],
      ])
    ).toBeNull()
  })
})

describe('routeToSvgPath', () => {
  const opts = { width: 64, height: 40, padding: 2 }

  it('returns a path starting with M and one L per extra point', () => {
    const d = routeToSvgPath(
      [
        [4.0, 45.0],
        [4.1, 45.1],
        [4.2, 45.0],
      ],
      opts
    )
    expect(d).not.toBeNull()
    expect(d?.startsWith('M')).toBe(true)
    expect((d?.match(/L/g) ?? []).length).toBe(2)
  })

  it('keeps every coordinate inside the padded box', () => {
    const d = routeToSvgPath(
      [
        [4.0, 45.0],
        [4.5, 45.4],
      ],
      opts
    )
    const nums = (d ?? '').match(/-?\d+(\.\d+)?/g)?.map(Number) ?? []
    const xs = nums.filter((_, i) => i % 2 === 0)
    const ys = nums.filter((_, i) => i % 2 === 1)
    expect(Math.min(...xs)).toBeGreaterThanOrEqual(opts.padding - 0.001)
    expect(Math.max(...xs)).toBeLessThanOrEqual(opts.width - opts.padding + 0.001)
    expect(Math.min(...ys)).toBeGreaterThanOrEqual(opts.padding - 0.001)
    expect(Math.max(...ys)).toBeLessThanOrEqual(opts.height - opts.padding + 0.001)
  })

  it('returns null for fewer than two points', () => {
    expect(routeToSvgPath([[4.0, 45.0]], opts)).toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- route-polyline`
Expected: FAIL (module introuvable).

- [ ] **Step 3: Write the implementation**

Create `lib/maps/route-polyline.ts` :

```ts
export type LngLat = [number, number]

function isLngLat(value: unknown): value is LngLat {
  if (!Array.isArray(value) || value.length < 2) return false
  const [lng, lat] = value
  return (
    typeof lng === 'number' &&
    typeof lat === 'number' &&
    lng >= -180 &&
    lng <= 180 &&
    lat >= -90 &&
    lat <= 90
  )
}

export function parseRoutePolyline(value: unknown): LngLat[] | null {
  if (!Array.isArray(value)) return null
  const points = value.filter(isLngLat).map(([lng, lat]) => [lng, lat] as LngLat)
  return points.length >= 2 ? points : null
}

interface SvgPathOpts {
  width: number
  height: number
  padding: number
}

export function routeToSvgPath(points: LngLat[], opts: SvgPathOpts): string | null {
  if (points.length < 2) return null

  const lats = points.map(([, lat]) => lat)
  const meanLat = lats.reduce((a, b) => a + b, 0) / lats.length
  const cosLat = Math.cos((meanLat * Math.PI) / 180)

  // Project to a planar space (equirectangular, longitude corrected by cos(lat)).
  const planar = points.map(([lng, lat]) => [lng * cosLat, lat] as LngLat)
  const xs = planar.map(([x]) => x)
  const ys = planar.map(([, y]) => y)
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)

  const usableW = opts.width - 2 * opts.padding
  const usableH = opts.height - 2 * opts.padding
  const spanX = maxX - minX || 1e-9
  const spanY = maxY - minY || 1e-9
  const scale = Math.min(usableW / spanX, usableH / spanY)

  // Centre the scaled drawing inside the padded box.
  const drawW = spanX * scale
  const drawH = spanY * scale
  const offsetX = opts.padding + (usableW - drawW) / 2
  const offsetY = opts.padding + (usableH - drawH) / 2

  const round = (n: number) => Math.round(n * 100) / 100
  const coords = planar.map(([x, y]) => {
    const px = offsetX + (x - minX) * scale
    // Invert Y: higher latitude should sit higher (smaller SVG y).
    const py = offsetY + (maxY - y) * scale
    return [round(px), round(py)] as LngLat
  })

  const [first, ...rest] = coords
  return `M${String(first[0])} ${String(first[1])}` + rest.map(([x, y]) => `L${String(x)} ${String(y)}`).join('')
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test -- route-polyline`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add lib/maps/route-polyline.ts tests/unit/maps/route-polyline.test.ts
git commit -m "feat(maps): parse route polyline jsonb and project to svg path"
```

---

## Task 2: Util `route-gradient` — couleur par métrique + expression line-gradient

**Files:**
- Create: `lib/maps/route-gradient.ts`
- Test: `tests/unit/maps/route-gradient.test.ts`

**Interfaces:**
- Consumes: `ActivitySample` (`@/lib/coach/activity-analysis`).
- Produces:
  - `type RouteMetric = 'hr' | 'speed' | 'elevation'`
  - `metricColor(t: number): string` — colormap bleu(0)→rouge(1) en HSL ; `t` clampé à `[0,1]`.
  - `METRIC_LABELS: Record<RouteMetric, string>` — libellés FR (`{ hr: 'FC', speed: 'Vitesse', elevation: 'Altitude' }`).
  - `availableMetrics(samples: ActivitySample[]): RouteMetric[]` — métriques ayant ≥ 2 valeurs numériques sur des points GPS.
  - `buildMetricGradient(samples: ActivitySample[], metric: RouteMetric): (string | number)[] | null` — expression MapLibre `['interpolate', ['linear'], ['line-progress'], f0, c0, ...]`, stops strictement croissants sur `[0,1]`. `null` si la trace ne permet pas un gradient (< 2 points GPS, distance nulle, ou aucune valeur métrique).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/maps/route-gradient.test.ts` :

```ts
import { describe, expect, it } from 'vitest'
import {
  availableMetrics,
  buildMetricGradient,
  metricColor,
} from '@/lib/maps/route-gradient'
import type { ActivitySample } from '@/lib/coach/activity-analysis'

function sample(partial: Partial<ActivitySample>): ActivitySample {
  return {
    sample_index: 0,
    sample_time: null,
    elapsed_s: null,
    distance_m: null,
    elevation_m: null,
    heart_rate_bpm: null,
    power_w: null,
    cadence_rpm: null,
    speed_m_s: null,
    latitude: null,
    longitude: null,
    ...partial,
  }
}

describe('metricColor', () => {
  it('returns distinct hsl colors across the range and clamps', () => {
    expect(metricColor(0)).toMatch(/^hsl\(/)
    expect(metricColor(1)).toMatch(/^hsl\(/)
    expect(metricColor(0)).not.toBe(metricColor(1))
    expect(metricColor(-5)).toBe(metricColor(0))
    expect(metricColor(5)).toBe(metricColor(1))
  })
})

describe('availableMetrics', () => {
  it('lists only metrics with at least two values on GPS points', () => {
    const samples = [
      sample({ latitude: 45.0, longitude: 4.0, heart_rate_bpm: 120, speed_m_s: 3 }),
      sample({ latitude: 45.1, longitude: 4.1, heart_rate_bpm: 140 }),
    ]
    expect(availableMetrics(samples)).toEqual(['hr'])
  })
})

describe('buildMetricGradient', () => {
  it('builds an interpolate expression with monotonic stops in [0,1]', () => {
    const samples = [
      sample({ latitude: 45.0, longitude: 4.0, heart_rate_bpm: 120 }),
      sample({ latitude: 45.1, longitude: 4.1, heart_rate_bpm: 150 }),
      sample({ latitude: 45.2, longitude: 4.2, heart_rate_bpm: 180 }),
    ]
    const expr = buildMetricGradient(samples, 'hr')
    expect(expr).not.toBeNull()
    expect(expr?.slice(0, 3)).toEqual(['interpolate', ['linear'], ['line-progress']])
    const stops = (expr ?? []).slice(3).filter((_, i) => i % 2 === 0) as number[]
    expect(stops[0]).toBe(0)
    expect(stops[stops.length - 1]).toBe(1)
    for (let i = 1; i < stops.length; i++) expect(stops[i]).toBeGreaterThan(stops[i - 1])
  })

  it('forward/back-fills missing metric values without dropping geometry', () => {
    const samples = [
      sample({ latitude: 45.0, longitude: 4.0, heart_rate_bpm: null }),
      sample({ latitude: 45.1, longitude: 4.1, heart_rate_bpm: 150 }),
      sample({ latitude: 45.2, longitude: 4.2, heart_rate_bpm: null }),
    ]
    const expr = buildMetricGradient(samples, 'hr')
    expect(expr).not.toBeNull()
  })

  it('returns null when fewer than two GPS points', () => {
    expect(
      buildMetricGradient([sample({ latitude: 45.0, longitude: 4.0, heart_rate_bpm: 120 })], 'hr')
    ).toBeNull()
  })

  it('returns null when no metric value exists', () => {
    const samples = [
      sample({ latitude: 45.0, longitude: 4.0 }),
      sample({ latitude: 45.1, longitude: 4.1 }),
    ]
    expect(buildMetricGradient(samples, 'hr')).toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- route-gradient`
Expected: FAIL (module introuvable).

- [ ] **Step 3: Write the implementation**

Create `lib/maps/route-gradient.ts` :

```ts
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
    .filter((s) => typeof s.latitude === 'number' && typeof s.longitude === 'number')
    .map((s) => ({
      lng: s.longitude as number,
      lat: s.latitude as number,
      value: typeof s[field] === 'number' ? (s[field] as number) : null,
    }))
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
  const meanLat = points.reduce((a, p) => a + p.lat, 0) / points.length
  const cosLat = Math.cos((meanLat * Math.PI) / 180)
  const distances: number[] = [0]
  for (let i = 1; i < points.length; i++) {
    const dx = (points[i].lng - points[i - 1].lng) * cosLat
    const dy = points[i].lat - points[i - 1].lat
    distances.push(distances[i - 1] + Math.hypot(dx, dy))
  }
  const total = distances[distances.length - 1]
  if (total <= 0) return null
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
    const normalized = span > 0 ? (values[i] - min) / span : 0.5
    stops.push(frac, metricColor(normalized))
  })

  if (stops.length < 4) return null
  return ['interpolate', ['linear'], ['line-progress'], ...stops]
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test -- route-gradient`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add lib/maps/route-gradient.ts tests/unit/maps/route-gradient.test.ts
git commit -m "feat(maps): build line-gradient expression colored by activity metric"
```

---

## Task 3: Util `heatmap-geojson` — agrégat des traces

**Files:**
- Create: `lib/maps/heatmap-geojson.ts`
- Test: `tests/unit/maps/heatmap-geojson.test.ts`

**Interfaces:**
- Consumes: `LngLat` (`@/lib/maps/route-polyline`).
- Produces:
  - `flattenRoutePoints(polylines: LngLat[][]): LngLat[]` — concatène tous les points.
  - `interface HeatmapFeatureCollection { type: 'FeatureCollection'; features: { type: 'Feature'; geometry: { type: 'Point'; coordinates: LngLat }; properties: Record<string, never> }[] }`
  - `buildHeatmapFeatureCollection(polylines: LngLat[][]): HeatmapFeatureCollection` — un `Point` GeoJSON par coordonnée.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/maps/heatmap-geojson.test.ts` :

```ts
import { describe, expect, it } from 'vitest'
import { buildHeatmapFeatureCollection, flattenRoutePoints } from '@/lib/maps/heatmap-geojson'

describe('flattenRoutePoints', () => {
  it('concatenates points from every polyline', () => {
    expect(
      flattenRoutePoints([
        [
          [4.0, 45.0],
          [4.1, 45.1],
        ],
        [[4.2, 45.2]],
      ])
    ).toEqual([
      [4.0, 45.0],
      [4.1, 45.1],
      [4.2, 45.2],
    ])
  })

  it('returns an empty array when there is no polyline', () => {
    expect(flattenRoutePoints([])).toEqual([])
  })
})

describe('buildHeatmapFeatureCollection', () => {
  it('emits one Point feature per coordinate', () => {
    const fc = buildHeatmapFeatureCollection([
      [
        [4.0, 45.0],
        [4.1, 45.1],
      ],
    ])
    expect(fc.type).toBe('FeatureCollection')
    expect(fc.features).toHaveLength(2)
    expect(fc.features[0]).toEqual({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [4.0, 45.0] },
      properties: {},
    })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- heatmap-geojson`
Expected: FAIL (module introuvable).

- [ ] **Step 3: Write the implementation**

Create `lib/maps/heatmap-geojson.ts` :

```ts
import type { LngLat } from '@/lib/maps/route-polyline'

export function flattenRoutePoints(polylines: LngLat[][]): LngLat[] {
  return polylines.flat()
}

interface HeatmapFeature {
  type: 'Feature'
  geometry: { type: 'Point'; coordinates: LngLat }
  properties: Record<string, never>
}

export interface HeatmapFeatureCollection {
  type: 'FeatureCollection'
  features: HeatmapFeature[]
}

export function buildHeatmapFeatureCollection(polylines: LngLat[][]): HeatmapFeatureCollection {
  return {
    type: 'FeatureCollection',
    features: flattenRoutePoints(polylines).map((coordinates) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates },
      properties: {},
    })),
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test -- heatmap-geojson`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add lib/maps/heatmap-geojson.ts tests/unit/maps/heatmap-geojson.test.ts
git commit -m "feat(maps): aggregate route polylines into heatmap geojson"
```

---

## Task 4: Composant `RouteThumbnail` — vignette SVG

**Files:**
- Create: `app/(app)/_components/maps/route-thumbnail.tsx`
- Test: `tests/unit/components/route-thumbnail.test.tsx`

**Interfaces:**
- Consumes: `parseRoutePolyline`, `routeToSvgPath` (Task 1).
- Produces: `RouteThumbnail({ polyline, className }: { readonly polyline: unknown; readonly className?: string })` — rend un `<svg>` avec un `<path>` de la trace, ou `null` si `polyline` invalide (< 2 points). Server-renderable (pas de `'use client'`).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/components/route-thumbnail.test.tsx` :

```tsx
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { RouteThumbnail } from '@/app/(app)/_components/maps/route-thumbnail'

describe('RouteThumbnail', () => {
  it('renders an svg path for a valid polyline', () => {
    const { container } = render(
      <RouteThumbnail
        polyline={[
          [4.0, 45.0],
          [4.1, 45.1],
          [4.2, 45.0],
        ]}
      />
    )
    const path = container.querySelector('path')
    expect(path).not.toBeNull()
    expect(path?.getAttribute('d')?.startsWith('M')).toBe(true)
  })

  it('renders nothing when the polyline is invalid', () => {
    const { container } = render(<RouteThumbnail polyline={null} />)
    expect(container.querySelector('svg')).toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- route-thumbnail`
Expected: FAIL (composant introuvable).

- [ ] **Step 3: Write the implementation**

Create `app/(app)/_components/maps/route-thumbnail.tsx` :

```tsx
import { parseRoutePolyline, routeToSvgPath } from '@/lib/maps/route-polyline'
import { cn } from '@/lib/utils'

const WIDTH = 64
const HEIGHT = 40
const PADDING = 3

interface RouteThumbnailProps {
  readonly polyline: unknown
  readonly className?: string
}

export function RouteThumbnail({ polyline, className }: RouteThumbnailProps) {
  const points = parseRoutePolyline(polyline)
  if (!points) return null
  const d = routeToSvgPath(points, { width: WIDTH, height: HEIGHT, padding: PADDING })
  if (!d) return null

  return (
    <svg
      width={WIDTH}
      height={HEIGHT}
      viewBox={`0 0 ${String(WIDTH)} ${String(HEIGHT)}`}
      className={cn('shrink-0', className)}
      role="img"
      aria-label="Aperçu du parcours GPS"
    >
      <path
        d={d}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        className="text-primary"
      />
    </svg>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test -- route-thumbnail`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add "app/(app)/_components/maps/route-thumbnail.tsx" tests/unit/components/route-thumbnail.test.tsx
git commit -m "feat(maps): add svg route thumbnail component"
```

---

## Task 5: Intégration vignette dans la liste historique

**Files:**
- Modify: `lib/dashboard/types.ts:36-46` (`ActivityRowDto`)
- Modify: `app/(app)/_components/activity-row.tsx`
- Modify: `app/(app)/history/page.tsx:46-48` (`select`)

**Interfaces:**
- Consumes: `RouteThumbnail` (Task 4).
- Produces: `ActivityRowDto` gagne `route_polyline?: unknown` ; `ActivityRow` rend la vignette entre l'icône sport et le bloc texte quand une trace existe.

- [ ] **Step 1: Étendre le DTO**

Dans `lib/dashboard/types.ts`, ajouter dans `interface ActivityRowDto` (après `hr_avg: number | null`) :

```ts
  route_polyline?: unknown
```

- [ ] **Step 2: Ajouter la vignette dans `ActivityRow`**

Dans `app/(app)/_components/activity-row.tsx`, ajouter l'import en tête (après l'import `sport-icon`) :

```ts
import { RouteThumbnail } from './maps/route-thumbnail'
```

Puis insérer la vignette juste après le `<Icon .../>` (avant le `<div className="min-w-0 flex-1">`) :

```tsx
      <RouteThumbnail polyline={activity.route_polyline} className="hidden sm:block" />
```

> `RouteThumbnail` rend `null` quand `route_polyline` est absent ou invalide, donc aucune réservation d'espace pour les activités indoor. La classe `hidden sm:block` masque la vignette sur très petit écran pour préserver la densité.

- [ ] **Step 3: Ajouter `route_polyline` au select historique**

Dans `app/(app)/history/page.tsx`, étendre le `select` des activités (lignes 46-48) :

```ts
    .select(
      'id, garmin_activity_id, start_time, sport, duration_s, distance_m, elevation_gain_m, tss, hr_avg, route_polyline'
    )
```

- [ ] **Step 4: Vérifier typecheck + lint + tests existants**

Run: `pnpm typecheck && pnpm lint && pnpm test -- activity-row route-thumbnail`
Expected: aucun problème ; tests verts.

> Note : si aucun test ne cible `activity-row` directement, la commande `pnpm test -- activity-row` n'exécute aucun fichier pour ce motif — c'est attendu. Le but est de confirmer que `route-thumbnail` reste vert et que rien ne casse au typecheck.

- [ ] **Step 5: Commit**

```bash
git add lib/dashboard/types.ts "app/(app)/_components/activity-row.tsx" "app/(app)/history/page.tsx"
git commit -m "feat(history): show route thumbnail in activity list rows"
```

---

## Task 6: Trace colorée par métrique sur le détail activité

**Files:**
- Modify: `app/(app)/_components/maps/activity-route-map.tsx`
- Test: `tests/unit/components/activity-route-map.test.tsx`

**Interfaces:**
- Consumes: `availableMetrics`, `buildMetricGradient`, `metricColor`, `METRIC_LABELS`, `RouteMetric` (Task 2) ; `buildRouteGeoJson`, `routeBounds` (existants).
- Produces: `ActivityRouteMap` rend toujours la carte, plus un toggle de métriques (« Aucune » + métriques disponibles). « Aucune » = trace cyan unie ; une métrique = `line-gradient`. La source GeoJSON est créée avec `lineMetrics: true` pour autoriser `line-gradient`.

- [ ] **Step 1: Write the failing test (toggle + gradient)**

Replace the whole content of `tests/unit/components/activity-route-map.test.tsx` with:

```tsx
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

const addSource = vi.fn()
const addLayer = vi.fn()
const fitBounds = vi.fn()
const setPaintProperty = vi.fn()
const on = vi.fn((event: string, cb: () => void) => {
  if (event === 'load') cb()
})

vi.mock('maplibre-gl', () => ({
  default: {
    Map: vi.fn(() => ({
      on,
      addSource,
      addLayer,
      fitBounds,
      setPaintProperty,
      remove: vi.fn(),
    })),
  },
}))

import { ActivityRouteMap } from '@/app/(app)/_components/maps/activity-route-map'
import type { ActivitySample } from '@/lib/coach/activity-analysis'

function sample(
  latitude: number | null,
  longitude: number | null,
  heart_rate_bpm: number | null = null
): ActivitySample {
  return {
    sample_index: 0,
    sample_time: null,
    elapsed_s: null,
    distance_m: null,
    elevation_m: null,
    heart_rate_bpm,
    power_w: null,
    cadence_rpm: null,
    speed_m_s: null,
    latitude,
    longitude,
  }
}

describe('ActivityRouteMap', () => {
  it('adds a line-metrics route source and fits bounds on load', () => {
    render(
      <ActivityRouteMap samples={[sample(45.1, 4.1, 120), sample(45.2, 4.2, 150)]} />
    )
    expect(addSource).toHaveBeenCalledWith(
      'route',
      expect.objectContaining({ lineMetrics: true })
    )
    expect(addLayer).toHaveBeenCalled()
    expect(fitBounds).toHaveBeenCalled()
  })

  it('switches to a metric gradient when a metric toggle is clicked', () => {
    setPaintProperty.mockClear()
    render(
      <ActivityRouteMap
        samples={[
          sample(45.1, 4.1, 120),
          sample(45.15, 4.15, 150),
          sample(45.2, 4.2, 180),
        ]}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: 'FC' }))
    expect(setPaintProperty).toHaveBeenCalledWith(
      'route-line',
      'line-gradient',
      expect.arrayContaining(['interpolate'])
    )
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- activity-route-map`
Expected: FAIL (`lineMetrics`/bouton `FC` absents).

- [ ] **Step 3: Write the implementation**

Replace the whole content of `app/(app)/_components/maps/activity-route-map.tsx` with:

```tsx
'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { buildRouteGeoJson, routeBounds } from '@/lib/maps/route-geojson'
import {
  availableMetrics,
  buildMetricGradient,
  METRIC_LABELS,
  metricColor,
  type RouteMetric,
} from '@/lib/maps/route-gradient'
import type { ActivitySample } from '@/lib/coach/activity-analysis'
import { cn } from '@/lib/utils'

const DARK_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'
const SOLID_COLOR = '#22d3ee'

interface ActivityRouteMapProps {
  readonly samples: ActivitySample[]
  readonly height?: number
}

// Uniform gradient used when no metric is selected (line-gradient needs line-progress).
function solidGradient(): (string | number)[] {
  return ['interpolate', ['linear'], ['line-progress'], 0, SOLID_COLOR, 1, SOLID_COLOR]
}

function paintFor(samples: ActivitySample[], metric: RouteMetric | null): (string | number)[] {
  if (metric === null) return solidGradient()
  return buildMetricGradient(samples, metric) ?? solidGradient()
}

export function ActivityRouteMap({ samples, height = 360 }: ActivityRouteMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const loadedRef = useRef(false)
  const [metric, setMetric] = useState<RouteMetric | null>(null)
  const metrics = useMemo(() => availableMetrics(samples), [samples])

  useEffect(() => {
    const container = containerRef.current
    const feature = buildRouteGeoJson(samples)
    if (!container || !feature) return

    const bounds = routeBounds(feature.geometry.coordinates)
    const map = new maplibregl.Map({
      container,
      style: DARK_STYLE,
      attributionControl: { compact: true },
    })
    mapRef.current = map
    loadedRef.current = false

    map.on('load', () => {
      map.addSource('route', { type: 'geojson', data: feature, lineMetrics: true })
      map.addLayer({
        id: 'route-line',
        type: 'line',
        source: 'route',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-width': 3, 'line-gradient': paintFor(samples, metric) },
      })
      if (bounds) map.fitBounds(bounds, { padding: 32, duration: 0 })
      loadedRef.current = true
    })

    return () => {
      loadedRef.current = false
      mapRef.current = null
      map.remove()
    }
    // Rebuild only when the trace itself changes; metric changes are applied below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [samples])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !loadedRef.current) return
    map.setPaintProperty('route-line', 'line-gradient', paintFor(samples, metric))
  }, [metric, samples])

  return (
    <div className="space-y-3">
      {metrics.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <ToggleButton active={metric === null} onClick={() => setMetric(null)} label="Aucune" />
          {metrics.map((m) => (
            <ToggleButton
              key={m}
              active={metric === m}
              onClick={() => setMetric(m)}
              label={METRIC_LABELS[m]}
            />
          ))}
          {metric !== null && <MetricLegend />}
        </div>
      )}
      <div className="relative">
        <span className="sr-only">Carte du parcours GPS de l&apos;activité</span>
        <div
          ref={containerRef}
          aria-hidden="true"
          style={{ height }}
          className="overflow-hidden rounded-md"
        />
      </div>
    </div>
  )
}

function ToggleButton({
  active,
  onClick,
  label,
}: {
  readonly active: boolean
  readonly onClick: () => void
  readonly label: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'rounded-md border px-3 py-1.5 text-xs',
        active
          ? 'bg-primary text-primary-foreground font-medium'
          : 'text-muted-foreground hover:bg-accent/50'
      )}
    >
      {label}
    </button>
  )
}

function MetricLegend() {
  return (
    <span className="text-muted-foreground ml-auto flex items-center gap-2 text-xs">
      <span>min</span>
      <span
        className="h-2 w-20 rounded"
        style={{ background: `linear-gradient(to right, ${metricColor(0)}, ${metricColor(0.5)}, ${metricColor(1)})` }}
      />
      <span>max</span>
    </span>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test -- activity-route-map`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add "app/(app)/_components/maps/activity-route-map.tsx" tests/unit/components/activity-route-map.test.tsx
git commit -m "feat(history): color activity route by hr/speed/elevation with toggle"
```

---

## Task 7: Composant heatmap + wrapper lazy

**Files:**
- Create: `app/(app)/_components/maps/routes-heatmap.tsx`
- Create: `app/(app)/_components/maps/routes-heatmap-lazy.tsx`
- Test: `tests/unit/components/routes-heatmap.test.tsx`

**Interfaces:**
- Consumes: `buildHeatmapFeatureCollection`, `flattenRoutePoints` (Task 3) ; `routeBounds` (existant) ; `LngLat` (Task 1).
- Produces:
  - `RoutesHeatmap({ polylines, height }: { readonly polylines: LngLat[][]; readonly height?: number })` — carte MapLibre avec couche `heatmap`. Rend `null` si aucun point.
  - `RoutesHeatmapLazy` — wrapper `dynamic(..., { ssr: false })`.

- [ ] **Step 1: Write the failing test (maplibre mocké)**

Create `tests/unit/components/routes-heatmap.test.tsx` :

```tsx
import { render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

const addSource = vi.fn()
const addLayer = vi.fn()
const fitBounds = vi.fn()
const on = vi.fn((event: string, cb: () => void) => {
  if (event === 'load') cb()
})

vi.mock('maplibre-gl', () => ({
  default: {
    Map: vi.fn(() => ({ on, addSource, addLayer, fitBounds, remove: vi.fn() })),
  },
}))

import { RoutesHeatmap } from '@/app/(app)/_components/maps/routes-heatmap'

describe('RoutesHeatmap', () => {
  it('adds a heatmap layer from the aggregated points', () => {
    render(
      <RoutesHeatmap
        polylines={[
          [
            [4.0, 45.0],
            [4.1, 45.1],
          ],
          [
            [4.2, 45.2],
            [4.3, 45.3],
          ],
        ]}
      />
    )
    expect(addSource).toHaveBeenCalledWith('routes', expect.anything())
    expect(addLayer).toHaveBeenCalledWith(expect.objectContaining({ type: 'heatmap' }))
    expect(fitBounds).toHaveBeenCalled()
  })

  it('renders nothing without points', () => {
    const { container } = render(<RoutesHeatmap polylines={[]} />)
    expect(container.firstChild).toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- routes-heatmap`
Expected: FAIL (composant introuvable).

- [ ] **Step 3: Write the implementation**

Create `app/(app)/_components/maps/routes-heatmap.tsx` :

```tsx
'use client'

import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { buildHeatmapFeatureCollection, flattenRoutePoints } from '@/lib/maps/heatmap-geojson'
import { routeBounds } from '@/lib/maps/route-geojson'
import type { LngLat } from '@/lib/maps/route-polyline'

const DARK_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'

interface RoutesHeatmapProps {
  readonly polylines: LngLat[][]
  readonly height?: number
}

export function RoutesHeatmap({ polylines, height = 360 }: RoutesHeatmapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const points = flattenRoutePoints(polylines)

  useEffect(() => {
    const container = containerRef.current
    if (!container || points.length === 0) return

    const data = buildHeatmapFeatureCollection(polylines)
    const bounds = routeBounds(points)
    const map = new maplibregl.Map({
      container,
      style: DARK_STYLE,
      attributionControl: { compact: true },
    })

    map.on('load', () => {
      map.addSource('routes', { type: 'geojson', data })
      map.addLayer({
        id: 'routes-heat',
        type: 'heatmap',
        source: 'routes',
        paint: {
          'heatmap-radius': 12,
          'heatmap-opacity': 0.85,
          'heatmap-intensity': 1,
        },
      })
      if (bounds) map.fitBounds(bounds, { padding: 32, duration: 0, maxZoom: 13 })
    })

    return () => {
      map.remove()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [polylines])

  if (points.length === 0) return null

  return (
    <div className="relative">
      <span className="sr-only">Carte de chaleur de tous tes parcours GPS</span>
      <div
        ref={containerRef}
        aria-hidden="true"
        style={{ height }}
        className="overflow-hidden rounded-md"
      />
    </div>
  )
}
```

Create `app/(app)/_components/maps/routes-heatmap-lazy.tsx` :

```tsx
'use client'

import dynamic from 'next/dynamic'
import type { LngLat } from '@/lib/maps/route-polyline'

const RoutesHeatmap = dynamic(() => import('./routes-heatmap').then((m) => m.RoutesHeatmap), {
  ssr: false,
})

interface RoutesHeatmapLazyProps {
  readonly polylines: LngLat[][]
  readonly height?: number
}

export function RoutesHeatmapLazy({ polylines, height }: RoutesHeatmapLazyProps) {
  return <RoutesHeatmap polylines={polylines} {...(height !== undefined && { height })} />
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test -- routes-heatmap`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add "app/(app)/_components/maps/routes-heatmap.tsx" "app/(app)/_components/maps/routes-heatmap-lazy.tsx" tests/unit/components/routes-heatmap.test.tsx
git commit -m "feat(maps): add global routes heatmap component"
```

---

## Task 8: Section heatmap « Où je m'entraîne » sur la page stats

**Files:**
- Modify: `app/(app)/stats/page.tsx` (`CockpitBody` : requête + section)

**Interfaces:**
- Consumes: `RoutesHeatmapLazy` (Task 7) ; `parseRoutePolyline` (Task 1) ; `ChartCard`, `EmptyState` (existants).
- Produces: une nouvelle section sous le cockpit affichant la heatmap de **toutes** les traces du user (indépendante du filtre range/sport).

- [ ] **Step 1: Importer les dépendances**

Dans `app/(app)/stats/page.tsx`, ajouter aux imports en tête :

```ts
import { RoutesHeatmapLazy } from '../_components/maps/routes-heatmap-lazy'
import { parseRoutePolyline, type LngLat } from '@/lib/maps/route-polyline'
```

- [ ] **Step 2: Charger les traces dans `CockpitBody`**

Dans `CockpitBody`, ajouter une 7ᵉ requête au `Promise.all` (lignes 98-143), après la requête `sleep` (la heatmap n'est pas filtrée par range : on récupère toutes les traces non nulles, plafonnées) :

```ts
      supabase
        .from('activities')
        .select('route_polyline')
        .eq('user_id', userId)
        .not('route_polyline', 'is', null)
        .limit(500),
```

Adapter la déstructuration du tuple pour capturer la nouvelle réponse :

```ts
  const [banisterRes, activitiesRes, plannedRes, feedbackRes, hrvRes, sleepRes, routesRes] =
    await Promise.all(
```

Puis, après la ligne `const sleep = (sleepRes.data ?? []) as SleepDto[]`, dériver les polylignes :

```ts
  const routePolylines: LngLat[][] = ((routesRes.data ?? []) as { route_polyline: unknown }[])
    .map((row) => parseRoutePolyline(row.route_polyline))
    .filter((poly): poly is LngLat[] => poly !== null)
```

- [ ] **Step 3: Rendre la section heatmap**

Dans le `return (...)` de `CockpitBody`, ajouter une nouvelle section juste avant la fermeture `</>` finale (après le bloc HRV/Sommeil) :

```tsx
      <section aria-labelledby="heatmap-title" className="space-y-3">
        <h2 id="heatmap-title" className="text-lg font-semibold">
          Où je m&apos;entraîne
        </h2>
        {routePolylines.length > 0 ? (
          <ChartCard
            title="Carte de chaleur"
            description="Toutes tes traces GPS cumulées (toutes périodes)."
          >
            <RoutesHeatmapLazy polylines={routePolylines} />
          </ChartCard>
        ) : (
          <EmptyState
            icon={ActivityIcon}
            title="Pas encore de trace GPS"
            description="Les parcours apparaîtront ici au fil des synchronisations Garmin."
          />
        )}
      </section>
```

> `ActivityIcon` et `EmptyState` sont déjà importés dans `stats/page.tsx` (vérifier en tête de fichier ; `ActivityIcon` vient de `lucide-react`, `EmptyState` de `../_components/empty-state`). S'ils manquent, les ajouter aux imports.

- [ ] **Step 4: Vérifier typecheck + lint + tests**

Run: `pnpm typecheck && pnpm lint && pnpm test -- maps`
Expected: aucun problème ; tests maps verts.

- [ ] **Step 5: Commit**

```bash
git add "app/(app)/stats/page.tsx"
git commit -m "feat(stats): add training heatmap section from all gps routes"
```

---

## Task 9: Vérification finale du livrable

- [ ] **Step 1: Suite frontend complète**

Run: `pnpm test && pnpm lint && pnpm typecheck && rm -rf .next && pnpm build`
Expected: tout vert (le `rm -rf .next` évite le cache stale entre branches — piège connu du projet).

- [ ] **Step 2: Vérification manuelle (recommandée)**

Avec au moins une activité possédant une `route_polyline` en base :
- `/history` : la vignette SVG apparaît sur les lignes vélo/course (rien sur indoor).
- `/history/<id>` : la carte affiche le toggle (Aucune / FC / Vitesse / Altitude) ; cliquer change la couleur de la trace, la légende min→max s'affiche.
- `/stats` : la section « Où je m'entraîne » montre la heatmap centrée sur les zones d'entraînement.

Si aucune activité n'a encore de GPS (backfill non exécuté), confirmer que les trois pages se rendent sans erreur (vignette absente, pas de carte sur le détail, EmptyState sur stats).

- [ ] **Step 3: Ouvrir la PR**

```bash
git push -u origin feat/carto-gps-livrable-b
gh pr create --base main \
  --title "feat: GPS routes — Livrable B (trace colorée, vignettes, heatmap)" \
  --body "Rendu enrichi des traces GPS : trace colorée par métrique sur le détail, vignettes SVG dans l'historique, heatmap globale sur stats. Frontend-only (consomme route_polyline + samples du Livrable A). Spec: docs/superpowers/specs/2026-06-24-gps-routes-maps-design.md"
```

Attendre la CI verte (lint, typecheck, test, build, audit, secrets, Sonar) avant merge.

---

## Self-Review (effectué)

**Couverture du spec (sous-spec §3 + critères de succès B)**
- Trace colorée par métrique (FC / vitesse / altitude) + toggle → Tasks 2 + 6. ✅ (critère 2)
- Vignette SVG sans coût réseau dans l'historique → Tasks 1 + 4 + 5. ✅ (critère 3)
- Heatmap globale sur la page stats → Tasks 3 + 7 + 8. ✅ (critère 4)
- Client-only WebGL (`ssr: false`) → carte détail (lazy existant), heatmap (Task 7 lazy). ✅
- Vignette = SVG pur, zéro WebGL/réseau → Task 4 (server-renderable). ✅
- Quality gates verts → Task 9. ✅ (critère 6)
- Critères 1 (trace sur carte) et 5 (backfill) → déjà couverts par le Livrable A (hors périmètre B).

**Placeholder scan** : aucun TBD/TODO ; tout le code est fourni ; les `eslint-disable` sont justifiés (effets MapLibre volontairement non ré-exécutés au changement de métrique). Pas de « add error handling » vague (parsing défensif explicite).

**Type consistency**
- `LngLat` défini Task 1, réutilisé Tasks 3, 7, 8. ✅
- `parseRoutePolyline(unknown) -> LngLat[] | null` : Task 1, consommé Tasks 4, 8. ✅
- `routeToSvgPath(points, opts) -> string | null` : Task 1, consommé Task 4. ✅
- `RouteMetric`, `availableMetrics`, `buildMetricGradient`, `metricColor`, `METRIC_LABELS` : Task 2, consommés Task 6. ✅
- `buildHeatmapFeatureCollection` / `flattenRoutePoints` : Task 3, consommés Task 7. ✅
- `RoutesHeatmapLazy({ polylines, height })` : Task 7, consommé Task 8. ✅
- `ActivityRowDto.route_polyline?: unknown` : Task 5, alimenté par le select Task 5, lu par `RouteThumbnail` Task 4. ✅
- `routeBounds` (existant) accepte `[number,number][]` = `LngLat[]` : compatible Tasks 6, 7. ✅
```
