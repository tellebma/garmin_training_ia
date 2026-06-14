'use server'

import { createClient } from '@/lib/supabase/server'
import { workerDailyBriefing } from '@/lib/worker'
import type { DailyBriefing } from '@/lib/coach/briefing-types'

type Result = { success: true; briefing: DailyBriefing } | { success: false; error: string }

function isFullBriefing(d: unknown): d is DailyBriefing {
  if (typeof d !== 'object' || d === null) return false
  if (!('readiness_score' in d)) return false
  if (!('activity_review' in d)) return false
  return typeof d.readiness_score === 'number'
}

export async function getDailyBriefing(): Promise<Result> {
  const supabase = await createClient()
  const { data } = await supabase.auth.getSession()
  const jwt = data.session?.access_token
  if (!jwt) return { success: false, error: 'unauthenticated' }
  try {
    const raw = await workerDailyBriefing(jwt)
    if (isFullBriefing(raw)) return { success: true, briefing: raw }
    if (typeof raw === 'object' && raw !== null && 'status' in raw) {
      return { success: false, error: String(raw.status) }
    }
    return { success: false, error: 'unknown_response' }
  } catch (e) {
    return { success: false, error: (e as Error).message }
  }
}
