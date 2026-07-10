import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'
import { getCurrentUser } from '@/lib/supabase/current-user'

/**
 * Use at the top of app/(app)/admin/page.tsx. Redirects:
 *  - to /login if the user isn't authenticated
 *  - to /today if the user is authenticated but not an admin
 *
 * Returns the authenticated user_id once both checks pass.
 *
 * Note: app/(app)/layout.tsx already checks is_admin_caller / is_feature_flag_active
 * for the maintenance-mode gate, so this re-check may look redundant. It is
 * intentional defense-in-depth — the admin page must not rely solely on the
 * shared layout for its own admin gate — not an oversight to be deduplicated.
 * (The underlying auth.getUser() call is shared via getCurrentUser()'s
 * request-scoped cache(); the is_admin_caller() RPC re-check itself still
 * runs independently here, on purpose.)
 */
export async function requireAdmin(): Promise<string> {
  const user = await getCurrentUser()
  if (!user) redirect('/login')

  const supabase = await createClient()
  const result = await supabase.rpc('is_admin_caller')
  const isAdmin = result.data as boolean | null
  if (!isAdmin) redirect('/today')

  return user.id
}
