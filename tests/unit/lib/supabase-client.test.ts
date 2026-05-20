import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

beforeAll(() => {
  process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co'
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'anon-key-test'
})

const createBrowserClient = vi.fn()
const createServerClient = vi.fn()
const cookiesMock = vi.fn()

vi.mock('@supabase/ssr', () => ({
  createBrowserClient: (...args: unknown[]) => createBrowserClient(...args) as unknown,
  createServerClient: (...args: unknown[]) => createServerClient(...args) as unknown,
}))

vi.mock('next/headers', () => ({
  cookies: () => cookiesMock() as unknown,
}))

describe('lib/supabase/client (browser)', () => {
  afterEach(() => {
    createBrowserClient.mockReset()
  })

  it('passes Supabase URL and anon key from env to createBrowserClient', async () => {
    createBrowserClient.mockReturnValueOnce({ marker: 'browser' })
    const { createClient } = await import('@/lib/supabase/client')
    const c = createClient()
    expect(c).toEqual({ marker: 'browser' })
    expect(createBrowserClient).toHaveBeenCalledTimes(1)
    const args = createBrowserClient.mock.calls[0] as unknown[]
    expect(args[0]).toMatch(/^https:\/\//)
    expect(args[1]).toBeTruthy()
  })
})

describe('lib/supabase/server', () => {
  afterEach(() => {
    createServerClient.mockReset()
    cookiesMock.mockReset()
  })

  it('passes the Next.js cookie store to createServerClient', async () => {
    const cookieStore = {
      getAll: vi.fn(() => [{ name: 'sb-access', value: 'xxx' }]),
      set: vi.fn(),
    }
    cookiesMock.mockReturnValue(Promise.resolve(cookieStore))
    createServerClient.mockReturnValueOnce({ marker: 'server' })
    const { createClient } = await import('@/lib/supabase/server')

    const c = await createClient()
    expect(c).toEqual({ marker: 'server' })
    expect(createServerClient).toHaveBeenCalledTimes(1)

    const args = createServerClient.mock.calls[0] as [string, string, { cookies: unknown }]
    expect(args[0]).toMatch(/^https:\/\//)
    expect(args[1]).toBeTruthy()
    const cookieAdapter = args[2].cookies as {
      getAll: () => unknown
      setAll: (list: { name: string; value: string; options?: unknown }[]) => void
    }
    expect(cookieAdapter.getAll()).toEqual([{ name: 'sb-access', value: 'xxx' }])

    cookieAdapter.setAll([{ name: 'foo', value: 'bar', options: { path: '/' } }])
    expect(cookieStore.set).toHaveBeenCalledWith('foo', 'bar', { path: '/' })
  })

  it('swallows cookie setAll errors (Server Component context)', async () => {
    const cookieStore = {
      getAll: vi.fn(() => []),
      set: vi.fn(() => {
        throw new Error('cannot set cookies in RSC')
      }),
    }
    cookiesMock.mockReturnValue(Promise.resolve(cookieStore))
    createServerClient.mockReturnValueOnce({})
    const { createClient } = await import('@/lib/supabase/server')

    await createClient()
    const args = createServerClient.mock.calls[0] as [string, string, { cookies: unknown }]
    const cookieAdapter = args[2].cookies as {
      setAll: (list: { name: string; value: string; options?: unknown }[]) => void
    }
    expect(() => {
      cookieAdapter.setAll([{ name: 'x', value: 'y' }])
    }).not.toThrow()
  })
})
