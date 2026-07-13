'use server'

import { createClient } from '@/lib/supabase/server'

export async function markChangelogSeen(version: string): Promise<{ success: boolean }> {
  const supabase = await createClient()
  const { data: sessionData } = await supabase.auth.getSession()
  const userId = sessionData.session?.user.id
  if (!userId) return { success: false }

  const { error } = await supabase
    .from('athlete_profiles')
    .update({ last_seen_changelog_version: version })
    .eq('user_id', userId)

  return { success: !error }
}
