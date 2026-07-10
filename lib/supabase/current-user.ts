import { cache } from 'react'
import type { User } from '@supabase/supabase-js'
import { createClient } from '@/lib/supabase/server'

/**
 * Returns the authenticated user for the current request, or null.
 *
 * Wrapped in React's `cache()` — Next.js App Router's "Request Memoization"
 * pattern (distinct from `unstable_cache`/`revalidate`, which persist across
 * requests). Within a single request's render pass, every caller sharing this
 * exact function reference (layout + every page guard) collapses onto a
 * single underlying `auth.getUser()` network call instead of one per caller.
 */
export const getCurrentUser = cache(async (): Promise<User | null> => {
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  return user
})
