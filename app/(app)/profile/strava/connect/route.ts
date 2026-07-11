import { NextResponse } from 'next/server'
import { requireOnboarded } from '@/lib/onboarding/guard'
import { getServerEnv } from '@/lib/env'

const STATE_COOKIE = 'strava_oauth_state'
const STATE_MAX_AGE_S = 600

export async function GET(request: Request): Promise<NextResponse> {
  await requireOnboarded()

  const { origin } = new URL(request.url)
  const state = crypto.randomUUID()
  const { STRAVA_CLIENT_ID } = getServerEnv()

  const authorizeUrl = new URL('https://www.strava.com/oauth/authorize')
  authorizeUrl.searchParams.set('client_id', STRAVA_CLIENT_ID)
  authorizeUrl.searchParams.set('response_type', 'code')
  authorizeUrl.searchParams.set('redirect_uri', `${origin}/profile/strava/callback`)
  authorizeUrl.searchParams.set('scope', 'activity:read_all')
  authorizeUrl.searchParams.set('state', state)

  const response = NextResponse.redirect(authorizeUrl, 307)
  response.cookies.set(STATE_COOKIE, state, {
    httpOnly: true,
    secure: true,
    sameSite: 'lax',
    maxAge: STATE_MAX_AGE_S,
    path: '/',
  })
  return response
}
