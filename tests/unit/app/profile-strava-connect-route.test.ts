import { beforeEach, describe, expect, it, vi } from 'vitest'

const requireOnboarded = vi.fn()
vi.mock('@/lib/onboarding/guard', () => ({
  requireOnboarded: (...a: unknown[]) => requireOnboarded(...a) as unknown,
}))

vi.mock('@/lib/env', () => ({
  getServerEnv: () => ({ WORKER_URL: 'http://localhost:8080', STRAVA_CLIENT_ID: 'client-123' }),
}))

import { GET } from '@/app/(app)/profile/strava/connect/route'

beforeEach(() => {
  requireOnboarded.mockReset()
  requireOnboarded.mockResolvedValue('u1')
})

describe('GET /profile/strava/connect', () => {
  it('redirects to the Strava authorize URL with a state param and sets a state cookie', async () => {
    const request = new Request('https://app.example.com/profile/strava/connect')

    const response = await GET(request)

    expect(response.status).toBe(307)
    const location = response.headers.get('location')
    expect(location).toContain('https://www.strava.com/oauth/authorize')
    expect(location).toContain('client_id=client-123')
    expect(location).toContain(
      'redirect_uri=https%3A%2F%2Fapp.example.com%2Fprofile%2Fstrava%2Fcallback'
    )
    expect(location).toContain('scope=activity%3Aread_all')
    const setCookie = response.headers.get('set-cookie')
    expect(setCookie).toContain('strava_oauth_state=')
    expect(setCookie).toContain('HttpOnly')
  })
})
