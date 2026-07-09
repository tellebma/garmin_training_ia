import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'

/**
 * Use at the top of app/(app)/admin/page.tsx. Redirects:
 *  - to /login if the user isn't authenticated
 *  - to /today if the user is authenticated but not an admin
 *
 * Returns the authenticated user_id once both checks pass.
 */
export async function requireAdmin(): Promise<string> {
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (!user) redirect('/login')

  const result = await supabase.rpc('is_admin_caller')
  const isAdmin = result.data as boolean | null
  if (!isAdmin) redirect('/today')

  return user.id
}
