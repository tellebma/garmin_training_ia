export interface RoutePoint {
  latitude: number | null
  longitude: number | null
}

export interface GeoJsonLineFeature {
  type: 'Feature'
  geometry: { type: 'LineString'; coordinates: [number, number][] }
  properties: Record<string, never>
}

function hasCoords(p: RoutePoint): p is { latitude: number; longitude: number } {
  return typeof p.latitude === 'number' && typeof p.longitude === 'number'
}

export function buildRouteGeoJson(samples: RoutePoint[]): GeoJsonLineFeature | null {
  const coordinates = samples
    .filter(hasCoords)
    .map((p) => [p.longitude, p.latitude] as [number, number])
  if (coordinates.length < 2) return null
  return { type: 'Feature', geometry: { type: 'LineString', coordinates }, properties: {} }
}

export function routeBounds(
  coords: [number, number][]
): [[number, number], [number, number]] | null {
  if (coords.length === 0) return null
  const first = coords[0]
  if (!first) return null
  let minLng = first[0]
  let maxLng = first[0]
  let minLat = first[1]
  let maxLat = first[1]
  for (const [lng, lat] of coords) {
    if (lng < minLng) minLng = lng
    if (lng > maxLng) maxLng = lng
    if (lat < minLat) minLat = lat
    if (lat > maxLat) maxLat = lat
  }
  return [
    [minLng, minLat],
    [maxLng, maxLat],
  ]
}
