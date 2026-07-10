'use client'

import { useEffect, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import type { ExpressionSpecification } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { buildRouteGeoJson, routeBounds } from '@/lib/maps/route-geojson'
import {
  availableMetrics,
  buildMetricGradient,
  METRIC_LABELS,
  type RouteMetric,
} from '@/lib/maps/route-gradient'
import { Button } from '@/components/ui/button'
import type { ActivitySample } from '@/lib/coach/activity-analysis'

const DARK_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'

const METRICS: readonly RouteMetric[] = ['hr', 'speed', 'elevation']

// Constant-colour fallback: same colour at both ends → flat cyan line.
const FALLBACK_GRADIENT = [
  'interpolate',
  ['linear'],
  ['line-progress'],
  0,
  '#22d3ee',
  1,
  '#22d3ee',
] as unknown as ExpressionSpecification

interface ActivityRouteMapProps {
  readonly samples: ActivitySample[]
  readonly height?: number
  readonly hoverIndex?: number | null
}

export function ActivityRouteMap({
  samples,
  height = 360,
  hoverIndex = null,
}: ActivityRouteMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const markerRef = useRef<maplibregl.Marker | null>(null)
  const [metric, setMetric] = useState<RouteMetric>('hr')

  // Keep a ref so the map 'load' handler always reads the latest metric
  // without requiring the whole map to be re-initialised.
  const metricRef = useRef<RouteMetric>(metric)
  useEffect(() => {
    metricRef.current = metric
  }, [metric])

  // Initialise the map once per samples set.
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

    map.on('load', () => {
      const gradient = buildMetricGradient(samples, metricRef.current)
      map.addSource('route', { type: 'geojson', data: feature, lineMetrics: true })
      map.addLayer({
        id: 'route-line',
        type: 'line',
        source: 'route',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-gradient':
            (gradient as unknown as ExpressionSpecification | null) ?? FALLBACK_GRADIENT,
          'line-width': 3,
        },
      })
      if (bounds) map.fitBounds(bounds, { padding: 32, duration: 0 })
    })

    return () => {
      mapRef.current = null
      markerRef.current = null
      map.remove()
    }
  }, [samples])

  // Update the gradient paint whenever metric or samples change (map already loaded).
  useEffect(() => {
    const map = mapRef.current
    if (!map?.isStyleLoaded() || !map.getLayer('route-line')) return
    const gradient = buildMetricGradient(samples, metric)
    map.setPaintProperty('route-line', 'line-gradient', gradient ?? FALLBACK_GRADIENT)
  }, [samples, metric])

  // Show/move a marker on the point that is currently hovered in the correlated chart.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const sample = hoverIndex === null ? undefined : samples[hoverIndex]
    if (!sample || typeof sample.latitude !== 'number' || typeof sample.longitude !== 'number') {
      markerRef.current?.remove()
      markerRef.current = null
      return
    }
    const lngLat: [number, number] = [sample.longitude, sample.latitude]
    if (markerRef.current) {
      markerRef.current.setLngLat(lngLat)
    } else {
      const el = document.createElement('div')
      el.className = 'h-3 w-3 rounded-full border-2 border-white bg-cyan-400 shadow'
      markerRef.current = new maplibregl.Marker({ element: el }).setLngLat(lngLat).addTo(map)
    }
  }, [hoverIndex, samples])

  const available = availableMetrics(samples)

  return (
    <div className="relative">
      {/* The canvas map is not screen-reader accessible — expose a text
          alternative and hide the visual map from assistive tech. */}
      <span className="sr-only">Carte du parcours GPS de l&apos;activité</span>
      {available.length > 0 && (
        <div className="absolute top-2 right-2 z-10 flex gap-1">
          {METRICS.filter((m) => available.includes(m)).map((m) => (
            <Button
              key={m}
              size="xs"
              variant={metric === m ? 'default' : 'outline'}
              onClick={() => {
                setMetric(m)
              }}
            >
              {METRIC_LABELS[m]}
            </Button>
          ))}
        </div>
      )}
      <div
        ref={containerRef}
        aria-hidden="true"
        style={{ height }}
        className="overflow-hidden rounded-md"
      />
    </div>
  )
}
