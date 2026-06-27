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
