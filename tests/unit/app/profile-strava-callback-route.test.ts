import { beforeEach, describe, expect, it, vi } from 'vitest'

const requireOnboarded = vi.fn()
vi.mock('@/lib/onboarding/guard', () => ({
  requireOnboarded: (...a: unknown[]) => requireOnboarded(...a) as unknown,
}))

const connectStrava = vi.fn()
vi.mock('@/app/actions/strava-auth', () => ({
  connectStrava: (...a: unknown[]) => connectStrava(...a) as unknown,
}))

import { GET } from '@/app/(app)/profile/strava/callback/route'

function requestWithCookie(url: string, cookieValue: string | null) {
  const headers = new Headers()
  if (cookieValue) headers.set('cookie', `strava_oauth_state=${cookieValue}`)
  return new Request(url, { headers })
}

beforeEach(() => {
  requireOnboarded.mockReset().mockResolvedValue('u1')
  connectStrava.mockReset()
})

describe('GET /profile/strava/callback', () => {
  it('redirects to /profile?strava=connected on success with matching state', async () => {
    connectStrava.mockResolvedValue({ status: 'connected' })
    const request = requestWithCookie(
      'https://app.example.com/profile/strava/callback?code=abc&state=xyz',
      'xyz'
    )

    const response = await GET(request)

    expect(connectStrava).toHaveBeenCalledWith('abc')
    expect(response.headers.get('location')).toBe(
      'https://app.example.com/profile?strava=connected'
    )
  })

  it('redirects to /profile?strava=error when state does not match the cookie', async () => {
    const request = requestWithCookie(
      'https://app.example.com/profile/strava/callback?code=abc&state=xyz',
      'different'
    )

    const response = await GET(request)

    expect(connectStrava).not.toHaveBeenCalled()
    expect(response.headers.get('location')).toBe('https://app.example.com/profile?strava=error')
  })

  it('redirects to /profile?strava=error when the code query param is missing', async () => {
    const request = requestWithCookie(
      'https://app.example.com/profile/strava/callback?state=xyz',
      'xyz'
    )

    const response = await GET(request)

    expect(connectStrava).not.toHaveBeenCalled()
    expect(response.headers.get('location')).toBe('https://app.example.com/profile?strava=error')
  })

  it('redirects to /profile?strava=error when the state query param is missing', async () => {
    const request = requestWithCookie(
      'https://app.example.com/profile/strava/callback?code=abc',
      'xyz'
    )

    const response = await GET(request)

    expect(connectStrava).not.toHaveBeenCalled()
    expect(response.headers.get('location')).toBe('https://app.example.com/profile?strava=error')
  })

  it('redirects to /profile?strava=error when there is no state cookie at all', async () => {
    const request = requestWithCookie(
      'https://app.example.com/profile/strava/callback?code=abc&state=xyz',
      null
    )

    const response = await GET(request)

    expect(connectStrava).not.toHaveBeenCalled()
    expect(response.headers.get('location')).toBe('https://app.example.com/profile?strava=error')
  })

  it('redirects to /profile?strava=error when the user denied authorization', async () => {
    const request = requestWithCookie(
      'https://app.example.com/profile/strava/callback?error=access_denied&state=xyz',
      'xyz'
    )

    const response = await GET(request)

    expect(connectStrava).not.toHaveBeenCalled()
    expect(response.headers.get('location')).toBe('https://app.example.com/profile?strava=error')
  })

  it('redirects to /profile?strava=error when the worker reports a non-connected status', async () => {
    connectStrava.mockResolvedValue({ status: 'strava_auth_error' })
    const request = requestWithCookie(
      'https://app.example.com/profile/strava/callback?code=abc&state=xyz',
      'xyz'
    )

    const response = await GET(request)

    expect(response.headers.get('location')).toBe('https://app.example.com/profile?strava=error')
  })
})
