'use client'

import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { buildRouteGeoJson, routeBounds } from '@/lib/maps/route-geojson'
import type { ActivitySample } from '@/lib/coach/activity-analysis'

const DARK_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'

interface ActivityRouteMapProps {
  readonly samples: ActivitySample[]
  readonly height?: number
}

export function ActivityRouteMap({ samples, height = 360 }: ActivityRouteMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const container = containerRef.current
    const feature = buildRouteGeoJson(samples)
    if (!container || !feature) return

    const bounds = routeBounds(feature.geometry.coordinates)
    const map = new maplibregl.Map({
      container,
      style: DARK_STYLE,
      attributionControl: false,
    })

    map.on('load', () => {
      map.addSource('route', { type: 'geojson', data: feature })
      map.addLayer({
        id: 'route-line',
        type: 'line',
        source: 'route',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': '#22d3ee', 'line-width': 3 },
      })
      if (bounds) map.fitBounds(bounds, { padding: 32, duration: 0 })
    })

    return () => {
      map.remove()
    }
  }, [samples])

  return <div ref={containerRef} style={{ height }} className="overflow-hidden rounded-md" />
}
