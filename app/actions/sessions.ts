'use server'

import { createClient } from '@/lib/supabase/server'
import { workerEnsureSessions, workerRegenerateSession } from '@/lib/worker'

type Result = { success: true; data: unknown } | { success: false; error: string }

async function getJwt(): Promise<string | null> {
  const supabase = await createClient()
  const { data } = await supabase.auth.getSession()
  return data.session?.access_token ?? null
}

function isStatusedError(data: unknown): data is { status: string } {
  return typeof data === 'object' && data !== null && 'status' in data
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
