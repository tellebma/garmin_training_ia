import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'

/**
 * Use at the top of any protected (non-onboarding) page. Redirects:
 *  - to /login if the user isn't authenticated
 *  - to /onboarding if onboarding_completed_at is null
 *
 * Returns the authenticated user_id once both checks pass.
 */
export async function requireOnboarded(): Promise<string> {
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (!user) redirect('/login')

  const { data } = await supabase
    .from('athlete_profiles')
    .select('onboarding_completed_at')
    .eq('user_id', user.id)
    .single<{ onboarding_completed_at: string | null }>()

  if (!data?.onboarding_completed_at) redirect('/onboarding')
  return user.id
}
