import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

beforeAll(() => {
  process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co'
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'anon-key-test'
})

const exchangeCodeForSession = vi.fn()
const getUser = vi.fn()
const fromMock = vi.fn()

vi.mock('@/lib/supabase/server', () => ({
  createClient: () =>
    Promise.resolve({
      auth: { exchangeCodeForSession, getUser },
      from: (...args: unknown[]) => fromMock(...args) as unknown,
    }),
}))

function mkProfileSelect(data: { password_set: boolean } | null) {
  const single = vi.fn().mockResolvedValue({ data })
  const eq = vi.fn(() => ({ single }))
  return { select: vi.fn(() => ({ eq })) }
}

beforeEach(() => {
  exchangeCodeForSession.mockReset()
  getUser.mockReset()
  fromMock.mockReset()
})

afterEach(() => {
  vi.resetModules()
})

describe('GET /auth/callback', () => {
  it('redirects to /login?error=auth_failed when code is missing', async () => {
    const { GET } = await import('@/app/(auth)/auth/callback/route')
    const res = await GET(new Request('https://app.test/auth/callback'))
    expect(res.status).toBe(307)
    expect(res.headers.get('location')).toBe('https://app.test/login?error=auth_failed')
  })

  it('redirects to /login?error=auth_failed when exchange fails', async () => {
    exchangeCodeForSession.mockResolvedValueOnce({ error: { message: 'invalid' } })
    const { GET } = await import('@/app/(auth)/auth/callback/route')
    const res = await GET(new Request('https://app.test/auth/callback?code=abc'))
    expect(res.headers.get('location')).toBe('https://app.test/login?error=auth_failed')
  })

  it('redirects to /auth/set-password when user.password_set is false', async () => {
    exchangeCodeForSession.mockResolvedValueOnce({ error: null })
    getUser.mockResolvedValueOnce({ data: { user: { id: 'u1' } } })
    fromMock.mockReturnValueOnce(mkProfileSelect({ password_set: false }))
    const { GET } = await import('@/app/(auth)/auth/callback/route')
    const res = await GET(new Request('https://app.test/auth/callback?code=abc&next=/today'))
    expect(res.headers.get('location')).toBe('https://app.test/auth/set-password')
  })

  it('honors next=/auth/reset-password even when password_set=false', async () => {
    exchangeCodeForSession.mockResolvedValueOnce({ error: null })
    getUser.mockResolvedValueOnce({ data: { user: { id: 'u1' } } })
    fromMock.mockReturnValueOnce(mkProfileSelect({ password_set: false }))
    const { GET } = await import('@/app/(auth)/auth/callback/route')
    const res = await GET(
      new Request('https://app.test/auth/callback?code=abc&next=/auth/reset-password')
    )
    expect(res.headers.get('location')).toBe('https://app.test/auth/reset-password')
  })

  it('redirects to next when password_set=true', async () => {
    exchangeCodeForSession.mockResolvedValueOnce({ error: null })
    getUser.mockResolvedValueOnce({ data: { user: { id: 'u1' } } })
    fromMock.mockReturnValueOnce(mkProfileSelect({ password_set: true }))
    const { GET } = await import('@/app/(auth)/auth/callback/route')
    const res = await GET(new Request('https://app.test/auth/callback?code=abc&next=/profile'))
    expect(res.headers.get('location')).toBe('https://app.test/profile')
  })

  it('defaults to safe next when no next param is provided', async () => {
    exchangeCodeForSession.mockResolvedValueOnce({ error: null })
    getUser.mockResolvedValueOnce({ data: { user: { id: 'u1' } } })
    fromMock.mockReturnValueOnce(mkProfileSelect({ password_set: true }))
    const { GET } = await import('@/app/(auth)/auth/callback/route')
    const res = await GET(new Request('https://app.test/auth/callback?code=abc'))
    // isSafeNext returns the default safe path
    expect(res.headers.get('location')).toMatch(/^https:\/\/app\.test\//)
  })
})
