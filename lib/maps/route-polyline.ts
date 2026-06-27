export type LngLat = [number, number]

function isLngLat(value: unknown): value is LngLat {
  if (!Array.isArray(value) || value.length < 2) return false
  const first = value[0] as unknown
  const second = value[1] as unknown
  return (
    typeof first === 'number' &&
    typeof second === 'number' &&
    first >= -180 &&
    first <= 180 &&
    second >= -90 &&
    second <= 90
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
  if (!first) return null
  return (
    `M${String(first[0])} ${String(first[1])}` +
    rest.map(([x, y]) => `L${String(x)} ${String(y)}`).join('')
  )
}
