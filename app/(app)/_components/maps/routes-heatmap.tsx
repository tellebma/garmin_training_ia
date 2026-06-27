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

    return () => {
      map.remove()
    }
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
