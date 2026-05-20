import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/headers', () => ({
  headers: vi.fn(),
}))

import { headers as mockHeaders } from 'next/headers'
import { clientIp, ipIsTrusted } from '@/lib/auth/client-ip'

function mkHeaders(map: Record<string, string | null>) {
  return Promise.resolve({
    get(name: string) {
      return map[name.toLowerCase()] ?? null
    },
  })
}

describe('clientIp', () => {
  beforeEach(() => {
    vi.mocked(mockHeaders).mockReset()
  })

  it('prefers x-vercel-forwarded-for left-most', async () => {
    vi.mocked(mockHeaders).mockReturnValue(
      mkHeaders({ 'x-vercel-forwarded-for': '1.2.3.4, 5.6.7.8' }) as ReturnType<typeof mockHeaders>
    )
    expect(await clientIp()).toBe('1.2.3.4')
  })

  it('falls back to x-real-ip when no vercel header', async () => {
    vi.mocked(mockHeaders).mockReturnValue(
      mkHeaders({ 'x-real-ip': '10.0.0.1' }) as ReturnType<typeof mockHeaders>
    )
    expect(await clientIp()).toBe('10.0.0.1')
  })

  it('falls back to x-forwarded-for left-most when no real-ip', async () => {
    vi.mocked(mockHeaders).mockReturnValue(
      mkHeaders({ 'x-forwarded-for': '8.8.8.8, 9.9.9.9' }) as ReturnType<typeof mockHeaders>
    )
    expect(await clientIp()).toBe('8.8.8.8')
  })

  it("returns 'unknown' when no source header is present", async () => {
    vi.mocked(mockHeaders).mockReturnValue(mkHeaders({}) as ReturnType<typeof mockHeaders>)
    expect(await clientIp()).toBe('unknown')
  })
})

describe('ipIsTrusted', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it("rejects 'unknown' in production (failure-closed)", () => {
    vi.stubEnv('NODE_ENV', 'production')
    expect(ipIsTrusted('unknown')).toBe(false)
  })

  it("accepts 'unknown' in dev/test (so local dev works)", () => {
    vi.stubEnv('NODE_ENV', 'development')
    expect(ipIsTrusted('unknown')).toBe(true)
  })

  it('always accepts a real IP', () => {
    vi.stubEnv('NODE_ENV', 'production')
    expect(ipIsTrusted('1.2.3.4')).toBe(true)
  })
})
