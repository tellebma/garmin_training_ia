import { NextResponse } from 'next/server'
import { requireOnboarded } from '@/lib/onboarding/guard'
import { connectStrava } from '@/app/actions/strava-auth'

const STATE_COOKIE = 'strava_oauth_state'

export async function GET(request: Request): Promise<NextResponse> {
  await requireOnboarded()

  const { searchParams, origin } = new URL(request.url)
  const code = searchParams.get('code')
  const state = searchParams.get('state')
  const deniedOrError = searchParams.get('error')
  const cookieHeader = request.headers.get('cookie') ?? ''
  const cookieState = cookieHeader
    .split(';')
    .map((c) => c.trim())
    .find((c) => c.startsWith(`${STATE_COOKIE}=`))
    ?.slice(STATE_COOKIE.length + 1)

  function redirectWithOutcome(outcome: 'connected' | 'error'): NextResponse {
    const response = NextResponse.redirect(`${origin}/profile?strava=${outcome}`)
    response.cookies.delete(STATE_COOKIE)
    return response
  }

  if (deniedOrError || !code || !state || !cookieState || state !== cookieState) {
    return redirectWithOutcome('error')
  }

  const result = await connectStrava(code)
  return redirectWithOutcome(result.status === 'connected' ? 'connected' : 'error')
}
