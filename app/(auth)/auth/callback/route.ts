// app/(auth)/auth/callback/route.ts
import { NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { isSafeNext } from '@/lib/auth/safe-next'

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url)
  const code = searchParams.get('code')
  const rawNext = searchParams.get('next')
  const next = isSafeNext(rawNext)

  if (!code) {
    return NextResponse.redirect(`${origin}/login?error=auth_failed`)
  }

  const supabase = await createClient()
  const { error } = await supabase.auth.exchangeCodeForSession(code)
  if (error) {
    return NextResponse.redirect(`${origin}/login?error=auth_failed`)
  }

  // Si l'user n'a pas encore set son mdp → toujours vers /auth/set-password
  // (sauf si on est explicitement sur le flow reset → /auth/reset-password)
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (user) {
    const { data: profile } = await supabase
      .from('athlete_profiles')
      .select('password_set')
      .eq('user_id', user.id)
      .single<{ password_set: boolean }>()

    if (profile?.password_set === false && next !== '/auth/reset-password') {
      return NextResponse.redirect(`${origin}/auth/set-password`)
    }
  }

  return NextResponse.redirect(`${origin}${next}`)
}
