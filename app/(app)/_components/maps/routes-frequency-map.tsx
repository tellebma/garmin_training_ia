'use client'

import { useEffect, useMemo, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import type { ExpressionSpecification } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import {
  buildRouteFrequencyGeoJson,
  frequencyLabels,
  FREQUENCY_COLORS,
  FREQUENCY_WIDTHS_HIGH,
  FREQUENCY_WIDTHS_LOW,
} from '@/lib/maps/route-frequency'

const DARK_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'
const LAYER_ID = 'routes-frequency'

/** ['step', ['get','passages'], out0, break1, out1, …] */
function stepExpression(
  breaks: readonly number[],
  outputs: readonly (string | number)[]
): ExpressionSpecification {
  const expression: unknown[] = ['step', ['get', 'passages'], outputs[0]]
  breaks.slice(1).forEach((lower, index) => {
    expression.push(lower, outputs[Math.min(index + 1, outputs.length - 1)])
  })
  return expression as unknown as ExpressionSpecification
}

/** Width grows with frequency AND with zoom, so classes stay separable dézoomé. */
function widthExpression(breaks: readonly number[]): ExpressionSpecification {
  return [
    'interpolate',
    ['linear'],
    ['zoom'],
    5,
    stepExpression(breaks, FREQUENCY_WIDTHS_LOW),
    13,
    stepExpression(breaks, FREQUENCY_WIDTHS_HIGH),
  ] as unknown as ExpressionSpecification
}

interface RoutesFrequencyMapProps {
  readonly polylines: unknown[]
  readonly height?: number
}

export function RoutesFrequencyMap({ polylines, height = 360 }: RoutesFrequencyMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const result = useMemo(() => buildRouteFrequencyGeoJson(polylines), [polylines])
  const { collection, breaks, maxPassages, bounds } = result
  const hasData = collection.features.length > 0

  useEffect(() => {
    const container = containerRef.current
    if (!container || !hasData) return

    const map = new maplibregl.Map({
      container,
      style: DARK_STYLE,
      attributionControl: { compact: true },
    })

    const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false })

    map.on('load', () => {
      map.addSource('routes', { type: 'geojson', data: collection })
      map.addLayer({
        id: LAYER_ID,
        type: 'line',
        source: 'routes',
        layout: {
          'line-cap': 'round',
          'line-join': 'round',
          // Busiest stretches drawn last so they are never hidden by a single pass.
          'line-sort-key': ['get', 'passages'] as unknown as ExpressionSpecification,
        },
        paint: {
          'line-color': stepExpression(breaks, FREQUENCY_COLORS),
          'line-width': widthExpression(breaks),
          'line-opacity': 0.9,
        },
      })
      if (bounds) map.fitBounds(bounds, { padding: 32, duration: 0 })
    })

    map.on('mousemove', LAYER_ID, (event) => {
      const passages = event.features?.[0]?.properties.passages as number | undefined
      if (passages === undefined) return
      map.getCanvas().style.cursor = 'pointer'
      popup
        .setLngLat(event.lngLat)
        .setText(`${String(passages)} passage${passages > 1 ? 's' : ''}`)
        .addTo(map)
    })
    map.on('mouseleave', LAYER_ID, () => {
      map.getCanvas().style.cursor = ''
      popup.remove()
    })

    return () => {
      popup.remove()
      map.remove()
    }
  }, [collection, breaks, bounds, hasData])

  if (!hasData) {
    return (
      <p className="text-muted-foreground text-sm">
        Pas encore assez de tracés GPS pour dessiner tes routes.
      </p>
    )
  }

  const labels = frequencyLabels(breaks, maxPassages)

  return (
    <div className="relative">
      {/* The canvas map is not screen-reader accessible — expose a text
          alternative and hide the visual map from assistive tech. */}
      <span className="sr-only">
        {`Carte de tes parcours GPS, pondérée par le nombre de passages : de 1 passage à ${String(maxPassages)} passages sur la route la plus empruntée.`}
      </span>
      <div
        ref={containerRef}
        aria-hidden="true"
        style={{ height }}
        className="overflow-hidden rounded-md"
      />
      <ul className="text-muted-foreground mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs">
        <li className="text-foreground/70">Passages</li>
        {labels.map((label, index) => (
          <li key={label} className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="inline-block rounded-full"
              style={{
                width: 18,
                height: Math.max(2, FREQUENCY_WIDTHS_HIGH[index] ?? 2),
                backgroundColor: FREQUENCY_COLORS[index],
              }}
            />
            {label}
          </li>
        ))}
      </ul>
    </div>
  )
}
