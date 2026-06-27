# Cartographie GPS — Livrable B (rendu enrichi) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exploiter `activities.route_polyline` (déjà rempli au sync) et les samples GPS pleine résolution pour offrir trois rendus carto : trace colorée par métrique sur le détail, vignettes SVG dans l'historique, et heatmap globale sur la page stats.

**Architecture:** Le livrable A a posé le pipeline data (migration `20260624000000_carto_gps.sql`, worker, `lib/maps/route-geojson.ts`, `ActivityRouteMap` sur le détail). Le livrable B est **purement frontend** : aucune migration, aucun changement worker. On ajoute des utils purs (testés en vitest) et des composants client-only MapLibre/SVG, en réutilisant les conventions existantes (`ChartCard`, tokens dark, `dynamic(..., { ssr: false })`).

**Tech Stack:** Next.js 15 (App Router, RSC), TypeScript strict, `maplibre-gl` (déjà installé), SVG inline, Vitest + Testing Library, Supabase JS.

## Global Constraints

- TypeScript strict — pas de `any`, props en `readonly`.
- Composants MapLibre **client-only** : `'use client'` + import via `dynamic(() => import(...), { ssr: false })`. Jamais de SSR WebGL.
- Vignette historique = **SVG pur**, zéro requête réseau, zéro instance WebGL (la liste peut afficher 20+ lignes).
- Thème dark : couleur de trace via token `--primary` (classe `text-primary` + `stroke="currentColor"`), fond CARTO dark `https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json`.
- Format `route_polyline` en DB : `jsonb` = liste de points `[lng, lat]` (≤ 64), ou `null`, ou `[]` (sentinelle « pas de GPS »). Traiter `null`, `[]` et `< 2 points` comme « pas de trace ».
- Quality gate SonarQube : 97 % coverage, gate enforced. Tout util a un test.
- Pas d'emoji dans l'UI (job CI « No emoji in UI »).
- Carte non accessible aux lecteurs d'écran → `aria-hidden` sur le canvas + alternative `sr-only` (pattern déjà en place dans `ActivityRouteMap`).

---

### Task 1: Util `polylineToSvgPath` (projection viewBox)

Util pur qui projette une `route_polyline` (`[lng, lat]`) en attributs SVG normalisés. Base de la vignette historique.

**Files:**
- Create: `lib/maps/route-thumbnail.ts`
- Test: `tests/unit/maps/route-thumbnail.test.ts`

**Interfaces:**
- Consumes: rien.
- Produces:
  - `type RoutePolyline = [number, number][]` (points `[lng, lat]`).
  - `interface SvgRoute { d: string; viewBox: string }`
  - `function polylineToSvgPath(polyline: unknown, size?: number): SvgRoute | null` — `size` par défaut `100`. Retourne `null` si `polyline` n'est pas un tableau d'au moins 2 points `[number, number]` valides, ou si la bbox est dégénérée (tous les points confondus).

- [ ] **Step 1: Write the failing test**

```typescript
// tests/unit/maps/route-thumbnail.test.ts
import { describe, expect, it } from 'vitest'
import { polylineToSvgPath } from '@/lib/maps/route-thumbnail'

describe('polylineToSvgPath', () => {
  it('projects a polyline into a normalized viewBox path (lat flipped on Y)', () => {
    const result = polylineToSvgPath(
      [
        [4.0, 45.0],
        [5.0, 46.0],
      ],
      100
    )
    expect(result).not.toBeNull()
    expect(result?.viewBox).toBe('0 0 100 100')
    // lng 4→5 maps x 0→100 ; lat 45 (min) is bottom → y=100, lat 46 (max) → y=0
    expect(result?.d).toBe('M0,100 L100,0')
  })

  it('returns null for fewer than 2 valid points', () => {
    expect(polylineToSvgPath([[4.0, 45.0]])).toBeNull()
    expect(polylineToSvgPath([])).toBeNull()
    expect(polylineToSvgPath(null)).toBeNull()
    expect(polylineToSvgPath('nope')).toBeNull()
  })

  it('returns null for a degenerate bbox (all points identical)', () => {
    expect(
      polylineToSvgPath([
        [4.0, 45.0],
        [4.0, 45.0],
      ])
    ).toBeNull()
  })

  it('preserves aspect ratio by centering the smaller axis', () => {
    // Wide-but-flat track: lng spans 0..10, lat spans 0..0.0001 → x uses full width,
    // y collapses near the vertical center (50).
    const result = polylineToSvgPath(
      [
        [0, 0],
        [10, 0.0001],
      ],
      100
    )
    expect(result?.d.startsWith('M0,')).toBe(true)
    expect(result?.d).toContain('L100,')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm vitest run tests/unit/maps/route-thumbnail.test.ts`
Expected: FAIL — `polylineToSvgPath` is not exported / module not found.

- [ ] **Step 3: Write minimal implementation**

```typescript
// lib/maps/route-thumbnail.ts
export type RoutePolyline = [number, number][]

export interface SvgRoute {
  d: string
  viewBox: string
}

function isPoint(value: unknown): value is [number, number] {
  return (
    Array.isArray(value) &&
    value.length >= 2 &&
    typeof value[0] === 'number' &&
    typeof value[1] === 'number' &&
    Number.isFinite(value[0]) &&
    Number.isFinite(value[1])
  )
}

export function polylineToSvgPath(polyline: unknown, size = 100): SvgRoute | null {
  if (!Array.isArray(polyline)) return null
  const points = polyline.filter(isPoint)
  if (points.length < 2) return null

  let minLng = points[0][0]
  let maxLng = points[0][0]
  let minLat = points[0][1]
  let maxLat = points[0][1]
  for (const [lng, lat] of points) {
    if (lng < minLng) minLng = lng
    if (lng > maxLng) maxLng = lng
    if (lat < minLat) minLat = lat
    if (lat > maxLat) maxLat = lat
  }

  const spanLng = maxLng - minLng
  const spanLat = maxLat - minLat
  if (spanLng === 0 && spanLat === 0) return null

  // Uniform scale on the larger span to preserve aspect ratio; center on the smaller axis.
  const span = Math.max(spanLng, spanLat)
  const offsetX = (span - spanLng) / 2
  const offsetY = (span - spanLat) / 2

  const project = ([lng, lat]: [number, number]): [number, number] => {
    const x = ((lng - minLng + offsetX) / span) * size
    // SVG Y grows downward → flip latitude.
    const y = size - ((lat - minLat + offsetY) / span) * size
    return [round(x), round(y)]
  }

  const d = points
    .map((p, i) => {
      const [x, y] = project(p)
      return `${i === 0 ? 'M' : 'L'}${x},${y}`
    })
    .join(' ')

  return { d, viewBox: `0 0 ${size} ${size}` }
}

function round(n: number): number {
  return Math.round(n * 100) / 100
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm vitest run tests/unit/maps/route-thumbnail.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add lib/maps/route-thumbnail.ts tests/unit/maps/route-thumbnail.test.ts
git commit -m "feat(carto): add polylineToSvgPath util for route thumbnails"
```

---

### Task 2: Composant `RouteThumbnail` (SVG pur)

Rendu SVG statique d'une polyline. Server-component compatible (pas de `'use client'`, pas de WebGL).

**Files:**
- Create: `app/(app)/_components/maps/route-thumbnail.tsx`
- Test: `tests/unit/components/route-thumbnail.test.tsx`

**Interfaces:**
- Consumes: `polylineToSvgPath`, `SvgRoute` de `@/lib/maps/route-thumbnail` (Task 1).
- Produces: `function RouteThumbnail(props: { readonly polyline: unknown; readonly size?: number; readonly className?: string }): JSX.Element | null` — retourne `null` quand `polylineToSvgPath` renvoie `null` (pas de placeholder, l'appelant gère l'absence).

- [ ] **Step 1: Write the failing test**

```tsx
// tests/unit/components/route-thumbnail.test.tsx
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { RouteThumbnail } from '@/app/(app)/_components/maps/route-thumbnail'

describe('RouteThumbnail', () => {
  it('renders an svg path for a valid polyline', () => {
    const { container } = render(
      <RouteThumbnail
        polyline={[
          [4.0, 45.0],
          [5.0, 46.0],
        ]}
      />
    )
    const path = container.querySelector('path')
    expect(path).not.toBeNull()
    expect(path?.getAttribute('d')).toBe('M0,100 L100,0')
    expect(container.querySelector('svg')?.getAttribute('viewBox')).toBe('0 0 100 100')
  })

  it('renders nothing when the polyline has no usable route', () => {
    const { container } = render(<RouteThumbnail polyline={[]} />)
    expect(container.querySelector('svg')).toBeNull()
  })

  it('renders nothing for the empty-array sentinel', () => {
    const { container } = render(<RouteThumbnail polyline={null} />)
    expect(container.firstChild).toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm vitest run tests/unit/components/route-thumbnail.test.tsx`
Expected: FAIL — module `route-thumbnail.tsx` not found.

- [ ] **Step 3: Write minimal implementation**

```tsx
// app/(app)/_components/maps/route-thumbnail.tsx
import { cn } from '@/lib/utils'
import { polylineToSvgPath } from '@/lib/maps/route-thumbnail'

interface RouteThumbnailProps {
  readonly polyline: unknown
  readonly size?: number
  readonly className?: string
}

export function RouteThumbnail({ polyline, size = 100, className }: RouteThumbnailProps) {
  const route = polylineToSvgPath(polyline, size)
  if (!route) return null

  return (
    <svg
      viewBox={route.viewBox}
      className={cn('text-primary', className)}
      role="img"
      aria-label="Aperçu du parcours"
      fill="none"
    >
      <path
        d={route.d}
        stroke="currentColor"
        strokeWidth={3}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm vitest run tests/unit/components/route-thumbnail.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/\(app\)/_components/maps/route-thumbnail.tsx tests/unit/components/route-thumbnail.test.tsx
git commit -m "feat(carto): add RouteThumbnail SVG component"
```

---

### Task 3: Intégration vignette dans l'historique

Charger `route_polyline` dans la liste et afficher la vignette dans chaque `ActivityRow`.

**Files:**
- Modify: `lib/dashboard/types.ts` (interface `ActivityRowDto`, ~ligne 36-46)
- Modify: `app/(app)/history/page.tsx` (le `.select(...)` des activities, ~ligne 44-47)
- Modify: `app/(app)/_components/activity-row.tsx` (ajouter la vignette)
- Test: `tests/unit/components/activity-row.test.tsx` (create si absent)

**Interfaces:**
- Consumes: `RouteThumbnail` (Task 2), `ActivityRowDto` étendu.
- Produces: `ActivityRowDto.route_polyline?: unknown` (optionnel, rétrocompat avec les autres appelants de `ActivityRow`).

- [ ] **Step 1: Write the failing test**

```tsx
// tests/unit/components/activity-row.test.tsx
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ActivityRow } from '@/app/(app)/_components/activity-row'
import type { ActivityRowDto } from '@/lib/dashboard/types'

const base: ActivityRowDto = {
  id: 'a1',
  garmin_activity_id: 1,
  start_time: '2026-06-20T07:00:00Z',
  sport: 'bike',
  duration_s: 3600,
  distance_m: 30000,
  elevation_gain_m: 400,
  tss: 80,
  hr_avg: 140,
}

describe('ActivityRow route thumbnail', () => {
  it('shows a route thumbnail when route_polyline has points', () => {
    const { container } = render(
      <ActivityRow
        activity={{
          ...base,
          route_polyline: [
            [4.0, 45.0],
            [5.0, 46.0],
          ],
        }}
      />
    )
    expect(container.querySelector('svg path')).not.toBeNull()
  })

  it('renders no thumbnail when route_polyline is the empty sentinel', () => {
    const { container } = render(<ActivityRow activity={{ ...base, route_polyline: [] }} />)
    expect(container.querySelector('svg path')).toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm vitest run tests/unit/components/activity-row.test.tsx`
Expected: FAIL — `route_polyline` not on `ActivityRowDto` (TS) and no svg rendered.

- [ ] **Step 3: Write minimal implementation**

In `lib/dashboard/types.ts`, add to `ActivityRowDto`:

```typescript
  hr_avg: number | null
  route_polyline?: unknown
```

In `app/(app)/history/page.tsx`, extend the select:

```typescript
    .select(
      'id, garmin_activity_id, start_time, sport, duration_s, distance_m, elevation_gain_m, tss, hr_avg, route_polyline'
    )
```

In `app/(app)/_components/activity-row.tsx`, import and render the thumbnail (replace the leading sport `Icon` block with icon + optional thumbnail):

```tsx
import { RouteThumbnail } from './maps/route-thumbnail'
```

Inside the row, right after the `<Icon .../>`:

```tsx
      <Icon size={20} className="text-muted-foreground shrink-0" aria-label={label} />
      {activity.route_polyline ? (
        <RouteThumbnail polyline={activity.route_polyline} className="h-8 w-8 shrink-0" />
      ) : null}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm vitest run tests/unit/components/activity-row.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Run typecheck**

Run: `pnpm typecheck`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add lib/dashboard/types.ts app/\(app\)/history/page.tsx app/\(app\)/_components/activity-row.tsx tests/unit/components/activity-row.test.tsx
git commit -m "feat(carto): show route thumbnail in history list"
```

---

### Task 4: Trace colorée par métrique sur le détail

Enrichir la carte du détail : ligne colorée par FC / vitesse / altitude via `line-gradient` + toggle.

**Files:**
- Create: `lib/maps/route-gradient.ts`
- Test: `tests/unit/maps/route-gradient.test.ts`
- Modify: `app/(app)/_components/maps/activity-route-map.tsx`

**Interfaces:**
- Consumes: `ActivitySample` de `@/lib/coach/activity-analysis` (a `latitude`, `longitude`, `heart_rate_bpm`, `speed_m_s`, `elevation_m`).
- Produces:
  - `type RouteMetric = 'hr' | 'speed' | 'elevation'`
  - `function buildGradientStops(samples, metric): [number, string][] | null` — paires `[lineProgress (0..1), couleur hex]` le long de la trace pour les samples GPS ; `null` si < 2 points GPS ou métrique absente sur tous les points.

- [ ] **Step 1: Write the failing test**

```typescript
// tests/unit/maps/route-gradient.test.ts
import { describe, expect, it } from 'vitest'
import { buildGradientStops } from '@/lib/maps/route-gradient'

const sample = (lat: number, lng: number, hr: number | null) => ({
  sample_index: 0,
  sample_time: null,
  elapsed_s: null,
  distance_m: null,
  elevation_m: null,
  heart_rate_bpm: hr,
  power_w: null,
  cadence_rpm: null,
  speed_m_s: null,
  latitude: lat,
  longitude: lng,
})

describe('buildGradientStops', () => {
  it('maps a metric to evenly spaced line-progress stops over GPS points', () => {
    const stops = buildGradientStops(
      [sample(45.0, 4.0, 120), sample(45.1, 4.1, 150), sample(45.2, 4.2, 180)],
      'hr'
    )
    expect(stops).not.toBeNull()
    expect(stops?.length).toBe(3)
    expect(stops?.[0][0]).toBe(0)
    expect(stops?.[2][0]).toBe(1)
    // low HR (120) and high HR (180) must yield different colors
    expect(stops?.[0][1]).not.toBe(stops?.[2][1])
  })

  it('returns null when fewer than 2 GPS points carry the metric', () => {
    expect(buildGradientStops([sample(45.0, 4.0, 120)], 'hr')).toBeNull()
    expect(
      buildGradientStops([sample(45.0, 4.0, null), sample(45.1, 4.1, null)], 'hr')
    ).toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm vitest run tests/unit/maps/route-gradient.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```typescript
// lib/maps/route-gradient.ts
import type { ActivitySample } from '@/lib/coach/activity-analysis'

export type RouteMetric = 'hr' | 'speed' | 'elevation'

const METRIC_KEY: Record<RouteMetric, keyof ActivitySample> = {
  hr: 'heart_rate_bpm',
  speed: 'speed_m_s',
  elevation: 'elevation_m',
}

// Blue (low) → red (high) ramp, readable on dark.
function rampColor(t: number): string {
  const hue = 220 - 220 * t // 220 (blue) → 0 (red)
  return `hsl(${Math.round(hue)}, 85%, 55%)`
}

function hasGps(s: ActivitySample): boolean {
  return typeof s.latitude === 'number' && typeof s.longitude === 'number'
}

export function buildGradientStops(
  samples: ActivitySample[],
  metric: RouteMetric
): [number, string][] | null {
  const key = METRIC_KEY[metric]
  const gps = samples.filter(hasGps)
  if (gps.length < 2) return null

  const values = gps.map((s) => s[key])
  const numeric = values.filter((v): v is number => typeof v === 'number')
  if (numeric.length < 2) return null

  const min = Math.min(...numeric)
  const max = Math.max(...numeric)
  const span = max - min || 1

  return gps.map((s, i) => {
    const progress = i / (gps.length - 1)
    const raw = s[key]
    const t = typeof raw === 'number' ? (raw - min) / span : 0
    return [progress, rampColor(t)]
  })
}
```

In `app/(app)/_components/maps/activity-route-map.tsx`:
- Add a `'use client'` state `metric` (`useState<RouteMetric>('hr')`) and three toggle buttons (reuse existing shadcn button conventions; labels « FC », « Vitesse », « Altitude »).
- The line layer must use a `line-gradient` paint built from `buildGradientStops`. MapLibre requires `lineMetrics: true` on the source and the layer expression `['interpolate', ['linear'], ['line-progress'], stop0, color0, stop1, color1, ...]`.
- Rebuild the gradient in an effect keyed on `[samples, metric]`. When `buildGradientStops` returns `null`, fall back to the existing solid `#22d3ee` line.

```tsx
// inside the load handler, replacing the static paint:
map.addSource('route', { type: 'geojson', data: feature, lineMetrics: true })
const stops = buildGradientStops(samples, metric)
const gradient = stops
  ? ['interpolate', ['linear'], ['line-progress'], ...stops.flat()]
  : null
map.addLayer({
  id: 'route-line',
  type: 'line',
  source: 'route',
  layout: { 'line-cap': 'round', 'line-join': 'round' },
  paint: gradient
    ? { 'line-gradient': gradient, 'line-width': 3 }
    : { 'line-color': '#22d3ee', 'line-width': 3 },
})
```

> Note: `line-gradient` requires `lineMetrics: true` and is incompatible with a constant `line-color`. Keep them mutually exclusive as above.

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm vitest run tests/unit/maps/route-gradient.test.ts`
Expected: PASS (2 tests).

- [ ] **Step 5: Typecheck + build**

Run: `pnpm typecheck && rm -rf .next && pnpm build`
Expected: no errors (the build exercises the client component bundling).

- [ ] **Step 6: Commit**

```bash
git add lib/maps/route-gradient.ts tests/unit/maps/route-gradient.test.ts app/\(app\)/_components/maps/activity-route-map.tsx
git commit -m "feat(carto): color activity route by metric (hr/speed/elevation)"
```

---

### Task 5: Heatmap globale sur la page stats

Section « Où je m'entraîne » : heatmap MapLibre de tous les `route_polyline`.

**Files:**
- Create: `app/(app)/_components/maps/routes-heatmap.tsx` (client, MapLibre)
- Create: `app/(app)/_components/maps/routes-heatmap-lazy.tsx` (dynamic ssr:false)
- Create: `lib/maps/heatmap-geojson.ts`
- Test: `tests/unit/maps/heatmap-geojson.test.ts`
- Modify: `app/(app)/stats/page.tsx` (requête + section)

**Interfaces:**
- Consumes: liste de `route_polyline` (chacun `[lng, lat][]` ou `null`/`[]`).
- Produces:
  - `function buildHeatmapGeoJson(polylines: unknown[]): { type: 'FeatureCollection'; features: ... }` — un `Feature` `Point` par coordonnée valide, agrégé sur toutes les traces. Ignore `null`, `[]`, points invalides.
  - `function RoutesHeatmapLazy(props: { readonly polylines: unknown[] }): JSX.Element`

- [ ] **Step 1: Write the failing test**

```typescript
// tests/unit/maps/heatmap-geojson.test.ts
import { describe, expect, it } from 'vitest'
import { buildHeatmapGeoJson } from '@/lib/maps/heatmap-geojson'

describe('buildHeatmapGeoJson', () => {
  it('flattens all valid polyline points into Point features', () => {
    const fc = buildHeatmapGeoJson([
      [
        [4.0, 45.0],
        [4.1, 45.1],
      ],
      [[5.0, 46.0]],
    ])
    expect(fc.type).toBe('FeatureCollection')
    expect(fc.features).toHaveLength(3)
    expect(fc.features[0].geometry).toEqual({ type: 'Point', coordinates: [4.0, 45.0] })
  })

  it('ignores null, empty sentinel, and malformed entries', () => {
    const fc = buildHeatmapGeoJson([null, [], 'nope', [[4.0, 45.0], ['x', 1]]])
    expect(fc.features).toHaveLength(1)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm vitest run tests/unit/maps/heatmap-geojson.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```typescript
// lib/maps/heatmap-geojson.ts
export interface HeatmapPoint {
  type: 'Feature'
  geometry: { type: 'Point'; coordinates: [number, number] }
  properties: Record<string, never>
}

export interface HeatmapCollection {
  type: 'FeatureCollection'
  features: HeatmapPoint[]
}

function isPoint(value: unknown): value is [number, number] {
  return (
    Array.isArray(value) &&
    typeof value[0] === 'number' &&
    typeof value[1] === 'number' &&
    Number.isFinite(value[0]) &&
    Number.isFinite(value[1])
  )
}

export function buildHeatmapGeoJson(polylines: unknown[]): HeatmapCollection {
  const features: HeatmapPoint[] = []
  for (const polyline of polylines) {
    if (!Array.isArray(polyline)) continue
    for (const point of polyline) {
      if (!isPoint(point)) continue
      features.push({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [point[0], point[1]] },
        properties: {},
      })
    }
  }
  return { type: 'FeatureCollection', features }
}
```

```tsx
// app/(app)/_components/maps/routes-heatmap.tsx
'use client'

import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { buildHeatmapGeoJson } from '@/lib/maps/heatmap-geojson'

const DARK_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'

interface RoutesHeatmapProps {
  readonly polylines: unknown[]
  readonly height?: number
}

export function RoutesHeatmap({ polylines, height = 360 }: RoutesHeatmapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const container = containerRef.current
    const data = buildHeatmapGeoJson(polylines)
    if (!container || data.features.length === 0) return

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
        paint: { 'heatmap-radius': 12, 'heatmap-opacity': 0.7 },
      })
      const bounds = new maplibregl.LngLatBounds()
      for (const f of data.features) bounds.extend(f.geometry.coordinates)
      if (!bounds.isEmpty()) map.fitBounds(bounds, { padding: 32, duration: 0 })
    })

    return () => map.remove()
  }, [polylines])

  return (
    <div className="relative">
      <span className="sr-only">Carte de chaleur de tous mes parcours GPS</span>
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

```tsx
// app/(app)/_components/maps/routes-heatmap-lazy.tsx
'use client'

import dynamic from 'next/dynamic'

const RoutesHeatmap = dynamic(() => import('./routes-heatmap').then((m) => m.RoutesHeatmap), {
  ssr: false,
})

interface RoutesHeatmapLazyProps {
  readonly polylines: unknown[]
}

export function RoutesHeatmapLazy({ polylines }: RoutesHeatmapLazyProps) {
  return <RoutesHeatmap polylines={polylines} />
}
```

In `app/(app)/stats/page.tsx`, add a query and a `ChartCard` section. Fetch only routes that have a real polyline:

```typescript
import { RoutesHeatmapLazy } from '../_components/maps/routes-heatmap-lazy'

// alongside the other queries:
const { data: routeRows } = await supabase
  .from('activities')
  .select('route_polyline')
  .eq('user_id', userId)
  .not('route_polyline', 'is', null)

const polylines = (routeRows ?? []).map((r) => r.route_polyline)
```

```tsx
{polylines.length > 0 && (
  <ChartCard title="Où je m'entraîne" description="Carte de chaleur de tes parcours GPS">
    <RoutesHeatmapLazy polylines={polylines} />
  </ChartCard>
)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm vitest run tests/unit/maps/heatmap-geojson.test.ts`
Expected: PASS (2 tests).

- [ ] **Step 5: Typecheck + build**

Run: `pnpm typecheck && rm -rf .next && pnpm build`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add lib/maps/heatmap-geojson.ts tests/unit/maps/heatmap-geojson.test.ts app/\(app\)/_components/maps/routes-heatmap.tsx app/\(app\)/_components/maps/routes-heatmap-lazy.tsx app/\(app\)/stats/page.tsx
git commit -m "feat(carto): add global routes heatmap on stats page"
```

---

### Task 6: Vérification finale + backlog

**Files:**
- Modify: `docs/superpowers/BACKLOG.md` (marquer E14.2 / sous-spec A livrable B)

- [ ] **Step 1: Full gates**

Run: `pnpm lint && pnpm typecheck && pnpm test && rm -rf .next && pnpm build`
Expected: all green.

- [ ] **Step 2: Update backlog**

Dans `docs/superpowers/BACKLOG.md`, sous E14.2 / la sous-spec carto, ajouter une note « Livrable B livré : trace colorée par métrique, vignettes SVG historique, heatmap stats ».

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/BACKLOG.md
git commit -m "docs(carto): mark livrable B (enriched rendering) delivered"
```

---

## Self-Review

**Spec coverage** (sous-spec carto, section « Livrable B ») :
- Trace colorée par métrique (toggle FC/vitesse/altitude) → Task 4. ✓
- Vignettes SVG dans l'historique → Tasks 1-3. ✓
- Heatmap globale sur stats → Task 5. ✓
- Critères de succès 2, 3, 4 → Tasks 4, 3, 5. ✓
- Critère 6 (gates verts) → Task 6. ✓
- Hors périmètre (PNG worker, GPX, édition) → non abordés. ✓

**Placeholder scan** : chaque step de code contient le code réel ; commandes exactes avec sortie attendue. ✓

**Type consistency** : `RoutePolyline`/`SvgRoute` (Task 1) consommés en Task 2 ; `ActivityRowDto.route_polyline` (Task 3) ; `RouteMetric`/`buildGradientStops` (Task 4) cohérents ; `buildHeatmapGeoJson`/`RoutesHeatmapLazy` (Task 5) cohérents. `polyline: unknown` partout pour absorber `null`/`[]`/jsonb sans cast. ✓

**Dépendance données** : le rendu réel dépend du backfill GPS en cours (worker corrigé, reset effectué). Les composants et utils sont testables sans données réelles ; les pages dégradent proprement quand `route_polyline` est `null`/`[]`/absent.
