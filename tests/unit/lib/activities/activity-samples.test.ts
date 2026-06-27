import { describe, expect, it } from 'vitest'
import { fetchAllActivitySamples } from '@/lib/activities/activity-samples'

/**
 * Fake Supabase query builder that emulates PostgREST's hard `max-rows` cap:
 * a single request never returns more than `serverCap` rows, regardless of the
 * requested `.range()` width. This is the exact behaviour that made `.limit(2000)`
 * silently return only 1000 rows.
 */
function makeClient(rows: unknown[], serverCap = 1000) {
  const rangeCalls: [number, number][] = []
  const builder = {
    select: () => builder,
    eq: () => builder,
    order: () => builder,
    range: (from: number, to: number) => {
      rangeCalls.push([from, to])
      const width = to - from + 1
      const slice = rows.slice(from, from + Math.min(width, serverCap))
      return Promise.resolve({ data: slice, error: null })
    },
  }
  return { client: { from: () => builder }, rangeCalls }
}

const params = { userId: 'u1', garminActivityId: 42 }

describe('fetchAllActivitySamples', () => {
  it('paginates past the 1000-row server cap to return every sample', async () => {
    const rows = Array.from({ length: 1730 }, (_, i) => ({ sample_index: i }))
    const { client, rangeCalls } = makeClient(rows)

    const result = await fetchAllActivitySamples(client as never, params)

    expect(result).toHaveLength(1730)
    expect(result[1729]).toEqual({ sample_index: 1729 })
    // Pages are 1000 wide so each request stays under the server cap.
    expect(rangeCalls).toEqual([
      [0, 999],
      [1000, 1999],
    ])
  })

  it('fetches the second page when the activity has exactly one full page (boundary)', async () => {
    // Exactly 1000 rows is the boundary that defined the original bug: the first
    // page is full (== pageSize) so the loop must request a second page, which
    // comes back empty and terminates.
    const rows = Array.from({ length: 1000 }, (_, i) => ({ sample_index: i }))
    const { client, rangeCalls } = makeClient(rows)

    const result = await fetchAllActivitySamples(client as never, params)

    expect(result).toHaveLength(1000)
    expect(rangeCalls).toEqual([
      [0, 999],
      [1000, 1999],
    ])
  })

  it('issues a single request when there are fewer than one page of samples', async () => {
    const rows = Array.from({ length: 500 }, (_, i) => ({ sample_index: i }))
    const { client, rangeCalls } = makeClient(rows)

    const result = await fetchAllActivitySamples(client as never, params)

    expect(result).toHaveLength(500)
    expect(rangeCalls).toEqual([[0, 999]])
  })

  it('stops at the safety cap (maxRows) for pathologically long activities', async () => {
    const rows = Array.from({ length: 9000 }, (_, i) => ({ sample_index: i }))
    const { client, rangeCalls } = makeClient(rows)

    const result = await fetchAllActivitySamples(client as never, params, {
      pageSize: 1000,
      maxRows: 4000,
    })

    expect(result).toHaveLength(4000)
    expect(rangeCalls).toEqual([
      [0, 999],
      [1000, 1999],
      [2000, 2999],
      [3000, 3999],
    ])
  })

  it('returns the rows gathered so far if a page errors', async () => {
    const builder = {
      select: () => builder,
      eq: () => builder,
      order: () => builder,
      range: () => Promise.resolve({ data: null, error: { message: 'boom' } }),
    }
    const client = { from: () => builder }

    const result = await fetchAllActivitySamples(client as never, params)

    expect(result).toEqual([])
  })
})
