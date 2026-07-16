const DEFAULT_RADIUS_KM = 50
const EARTH_RADIUS_KM = 6371

export type ColType = 'col' | 'peak'

export interface ColDto {
  id: string
  name: string
  latitude: number
  longitude: number
  elevation_m: number | null
  type: ColType
}

export interface ColCrossingRowDto {
  col_id: string
  crossed_at: string
}

export interface ColSummary {
  id: string
  name: string
  elevationM: number | null
  distanceKm: number
  crossingsCount: number
  lastCrossedAt: string | null
  type: ColType
}

export interface GroupedColsSummary {
  cols: ColSummary[]
  peaks: ColSummary[]
}

export function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180
  const dLat = toRad(lat2 - lat1)
  const dLon = toRad(lon2 - lon1)
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(a))
}

export function computeColsSummary({
  homeLat,
  homeLon,
  cols,
  crossings,
  radiusKm = DEFAULT_RADIUS_KM,
}: {
  homeLat: number
  homeLon: number
  cols: ColDto[]
  crossings: ColCrossingRowDto[]
  radiusKm?: number
}): GroupedColsSummary {
  const crossingsByCol = new Map<string, { count: number; lastCrossedAt: string }>()
  for (const crossing of crossings) {
    const existing = crossingsByCol.get(crossing.col_id)
    if (!existing) {
      crossingsByCol.set(crossing.col_id, { count: 1, lastCrossedAt: crossing.crossed_at })
      continue
    }
    existing.count += 1
    if (crossing.crossed_at > existing.lastCrossedAt) {
      existing.lastCrossedAt = crossing.crossed_at
    }
  }

  const summaries: (ColSummary & { _distanceKm: number })[] = cols
    .map((col): ColSummary & { _distanceKm: number } => {
      const distanceKm = haversineKm(homeLat, homeLon, col.latitude, col.longitude)
      const crossing = crossingsByCol.get(col.id)
      return {
        id: col.id,
        name: col.name,
        elevationM: col.elevation_m,
        distanceKm: Math.round(distanceKm * 10) / 10,
        crossingsCount: crossing?.count ?? 0,
        lastCrossedAt: crossing?.lastCrossedAt ?? null,
        type: col.type,
        _distanceKm: distanceKm,
      }
    })
    .filter((summary) => summary._distanceKm <= radiusKm)

  const sorted = summaries
    .toSorted((a, b) => b.crossingsCount - a.crossingsCount || a.distanceKm - b.distanceKm)
    .map(({ _distanceKm, ...summary }) => summary)

  return {
    cols: sorted.filter((summary) => summary.type === 'col'),
    peaks: sorted.filter((summary) => summary.type === 'peak'),
  }
}

interface EmbeddedCol {
  name: string
  elevation_m: number | null
}

export interface ActivityColCrossingRowDto {
  col_id: string
  crossed_at: string
  // PostgREST embeds a to-one relation as a single object at runtime (col_crossings.col_id
  // is a many-to-one FK to cols), but this project's untyped Supabase client infers embedded
  // relations as arrays regardless of cardinality — accept both shapes honestly instead of
  // asserting the narrower one away.
  cols: EmbeddedCol | EmbeddedCol[]
}

export interface ActivityColCrossingDto {
  colId: string
  name: string
  elevationM: number | null
  crossedAt: string
}

function firstCol(cols: EmbeddedCol | EmbeddedCol[]): EmbeddedCol | undefined {
  return Array.isArray(cols) ? cols[0] : cols
}

export function toActivityColCrossings(
  rows: ActivityColCrossingRowDto[]
): ActivityColCrossingDto[] {
  return rows
    .flatMap((r) => {
      const col = firstCol(r.cols)
      if (!col) return []
      return [
        { colId: r.col_id, name: col.name, elevationM: col.elevation_m, crossedAt: r.crossed_at },
      ]
    })
    .toSorted((a, b) => a.crossedAt.localeCompare(b.crossedAt))
}
