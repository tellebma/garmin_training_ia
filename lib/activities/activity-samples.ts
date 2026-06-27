import type { SupabaseClient } from '@supabase/supabase-js'
import type { ActivitySample } from '@/lib/coach/activity-analysis'

const SAMPLE_COLUMNS =
  'sample_index, sample_time, elapsed_s, distance_m, elevation_m, heart_rate_bpm, power_w, cadence_rpm, speed_m_s, latitude, longitude'

// PostgREST enforces a server-side `max-rows` cap (1000 by default) that silently
// overrides a larger `.limit(...)`. We therefore page through the samples in
// PAGE_SIZE-wide windows (each at/under the cap) until the activity is exhausted.
const PAGE_SIZE = 1000
// Safety ceiling so a pathological activity can't trigger unbounded paging.
const MAX_ROWS = 5000

interface FetchParams {
  userId: string
  garminActivityId: number
}

interface FetchOptions {
  pageSize?: number
  maxRows?: number
}

/**
 * Fetch every `activity_samples` row for one activity, paginating around the
 * PostgREST `max-rows` cap. Returns the rows gathered so far if a page errors.
 */
export async function fetchAllActivitySamples(
  client: SupabaseClient,
  params: FetchParams,
  opts: FetchOptions = {}
): Promise<ActivitySample[]> {
  const pageSize = opts.pageSize ?? PAGE_SIZE
  const maxRows = opts.maxRows ?? MAX_ROWS
  const all: ActivitySample[] = []

  for (let offset = 0; offset < maxRows; offset += pageSize) {
    const to = Math.min(offset + pageSize, maxRows) - 1
    const { data, error } = await client
      .from('activity_samples')
      .select(SAMPLE_COLUMNS)
      .eq('user_id', params.userId)
      .eq('garmin_activity_id', params.garminActivityId)
      .order('sample_index', { ascending: true })
      .range(offset, to)

    if (error) {
      // Surface partial-pagination failures so a truncated render is diagnosable
      // instead of silently swallowed (same failure class this helper fixes).
      console.error('fetchAllActivitySamples: page failed, returning partial set', error)
      break
    }
    const rows = data as ActivitySample[]
    all.push(...rows)
    if (rows.length < pageSize) break
  }

  return all
}
