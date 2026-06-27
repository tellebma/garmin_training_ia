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

  let minLng = Infinity
  let maxLng = -Infinity
  let minLat = Infinity
  let maxLat = -Infinity
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
      return (i === 0 ? 'M' : 'L') + String(x) + ',' + String(y)
    })
    .join(' ')

  return { d, viewBox: '0 0 ' + String(size) + ' ' + String(size) }
}

function round(n: number): number {
  return Math.round(n * 100) / 100
}
