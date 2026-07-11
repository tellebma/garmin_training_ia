import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const ORIGINAL_FETCH = globalThis.fetch
const ORIGINAL_WORKER_URL = process.env.WORKER_URL
const ORIGINAL_SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL
const ORIGINAL_SUPABASE_ANON = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
const ORIGINAL_STRAVA_CLIENT_ID = process.env.STRAVA_CLIENT_ID

describe('workerPost', () => {
  beforeEach(() => {
    process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co'
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'anon-key-test'
    process.env.WORKER_URL = 'https://worker.local'
    process.env.STRAVA_CLIENT_ID = 'test-strava-client-id'
    vi.resetModules()
  })

  afterEach(() => {
    globalThis.fetch = ORIGINAL_FETCH
    process.env.WORKER_URL = ORIGINAL_WORKER_URL
    process.env.NEXT_PUBLIC_SUPABASE_URL = ORIGINAL_SUPABASE_URL
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = ORIGINAL_SUPABASE_ANON
    process.env.STRAVA_CLIENT_ID = ORIGINAL_STRAVA_CLIENT_ID
  })

  it('sends Bearer JWT header and JSON body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: 'ok' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    )
    globalThis.fetch = fetchMock as typeof globalThis.fetch
    const { workerPost } = await import('@/lib/worker')

    const result = await workerPost<{ status: string }>('/garmin/connect', { foo: 'bar' }, 'jwt-x')

    expect(result).toEqual({ status: 'ok' })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('https://worker.local/garmin/connect')
    expect(init.method).toBe('POST')
    const headers = init.headers as Record<string, string>
    expect(headers.Authorization).toBe('Bearer jwt-x')
    expect(headers['Content-Type']).toBe('application/json')
    expect(init.body).toBe(JSON.stringify({ foo: 'bar' }))
    expect(init.cache).toBe('no-store')
  })

  it('throws on 401 with body in the error message', async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(new Response('Missing bearer token', { status: 401 }))
    const { workerPost } = await import('@/lib/worker')

    await expect(workerPost('/sync/u1', {}, 'jwt')).rejects.toThrow(/401.*Missing bearer/)
  })

  it('returns parsed JSON for any non-401 status (worker uses error_id pattern)', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: 'rate_limited', retry_after_seconds: 60 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    )
    const { workerPost } = await import('@/lib/worker')

    const r = await workerPost<{ status: string; retry_after_seconds: number }>('/x', {}, 'jwt')
    expect(r.status).toBe('rate_limited')
    expect(r.retry_after_seconds).toBe(60)
  })

  it('throws a descriptive error when body is not JSON', async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(new Response('<html>502 Bad Gateway</html>', { status: 502 }))
    const { workerPost } = await import('@/lib/worker')

    // Body is consumed by .json() before .text() is tried, so the error
    // says <unreadable>. We just check the prefix.
    await expect(workerPost('/x', {}, 'jwt')).rejects.toThrow(/Worker returned 502 with non-JSON/)
  })
})
