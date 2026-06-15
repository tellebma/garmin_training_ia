'use server'

import { revalidatePath } from 'next/cache'
import { createClient } from '@/lib/supabase/server'
import { workerEnsureSessions, workerRegenerateSession } from '@/lib/worker'

type Result = { success: true; data: unknown } | { success: false; error: string }
type SessionType = 'endurance' | 'threshold' | 'intervals' | 'long' | 'recovery' | 'race' | 'rest'

const ALLOWED_SESSION_TYPES = new Set<SessionType>([
  'endurance',
  'threshold',
  'intervals',
  'long',
  'recovery',
  'race',
  'rest',
])

async function getJwt(): Promise<string | null> {
  const supabase = await createClient()
  const { data } = await supabase.auth.getSession()
  return data.session?.access_token ?? null
}

function isStatusedError(data: unknown): data is { status: string } {
  return typeof data === 'object' && data !== null && 'status' in data
}

function parseSessionType(value: string): SessionType | null {
  return ALLOWED_SESSION_TYPES.has(value as SessionType) ? (value as SessionType) : null
}

function adjustedTargets(
  sessionType: SessionType,
  current: { target_duration_s?: number | null; target_tss?: number | null }
): {
  sport?: 'rest'
  target_duration_s?: number
  target_tss?: number
} {
  if (sessionType === 'rest') {
    return { sport: 'rest', target_duration_s: 0, target_tss: 0 }
  }
  if (sessionType === 'recovery') {
    return {
      target_duration_s: Math.min(current.target_duration_s ?? 2400, 2400),
      target_tss: Math.min(current.target_tss ?? 30, 30),
    }
  }
  if (sessionType === 'endurance') {
    return {
      target_tss: Math.min(current.target_tss ?? 60, 60),
    }
  }
  return {}
}

export async function ensureGeneratedSessions(days = 7): Promise<Result> {
  const jwt = await getJwt()
  if (!jwt) return { success: false, error: 'unauthenticated' }
  try {
    const data = await workerEnsureSessions(jwt, days)
    if (isStatusedError(data) && data.status === 'rate_limited') {
      return { success: false, error: 'rate_limited' }
    }
    return { success: true, data }
  } catch (e) {
    return { success: false, error: (e as Error).message }
  }
}

export async function applySessionAdjustment(
  sessionId: string,
  suggestedSessionType: string
): Promise<Result> {
  const supabase = await createClient()
  const { data } = await supabase.auth.getSession()
  const userId = data.session?.user.id
  if (!userId) return { success: false, error: 'unauthenticated' }

  const sessionType = parseSessionType(suggestedSessionType)
  if (!sessionType) return { success: false, error: 'invalid_session_type' }

  const { data: current, error: readError } = await supabase
    .from('planned_sessions')
    .select('id, user_id, target_duration_s, target_tss')
    .eq('id', sessionId)
    .eq('user_id', userId)
    .maybeSingle()

  if (readError) return { success: false, error: readError.message }
  if (!current) return { success: false, error: 'session_not_found' }

  const updatePayload = {
    session_type: sessionType,
    workout: null,
    workout_generated_at: null,
    ...adjustedTargets(sessionType, current),
  }
  const { error: updateError } = await supabase
    .from('planned_sessions')
    .update(updatePayload)
    .eq('id', sessionId)
    .eq('user_id', userId)

  if (updateError) return { success: false, error: updateError.message }
  revalidatePath('/today')
  revalidatePath('/plan')
  return { success: true, data: { status: 'ok', session_type: sessionType } }
}

export async function regenerateSession(sessionId: string): Promise<Result> {
  const jwt = await getJwt()
  if (!jwt) return { success: false, error: 'unauthenticated' }
  try {
    const data = await workerRegenerateSession(jwt, sessionId)
    if (isStatusedError(data) && data.status === 'rate_limited') {
      return { success: false, error: 'rate_limited' }
    }
    if (isStatusedError(data) && data.status === 'session_not_found') {
      return { success: false, error: 'session_not_found' }
    }
    return { success: true, data }
  } catch (e) {
    return { success: false, error: (e as Error).message }
  }
}
