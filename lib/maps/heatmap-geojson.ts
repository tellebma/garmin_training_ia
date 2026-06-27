import { isLngLat } from './geo'

export interface HeatmapPoint {
  type: 'Feature'
  geometry: { type: 'Point'; coordinates: [number, number] }
  properties: Record<string, never>
}

export interface HeatmapCollection {
  type: 'FeatureCollection'
  features: HeatmapPoint[]
}

export function buildHeatmapGeoJson(polylines: unknown[]): HeatmapCollection {
  const features: HeatmapPoint[] = []
  for (const polyline of polylines) {
    if (!Array.isArray(polyline)) continue
    for (const point of polyline) {
      if (!isLngLat(point)) continue
      features.push({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [point[0], point[1]] },
        properties: {},
      })
    }
  }
  return { type: 'FeatureCollection', features }
}
