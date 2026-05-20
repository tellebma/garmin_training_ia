'use server'

import { createClient } from '@/lib/supabase/server'
import { workerEnsureSessions, workerRegenerateSession } from '@/lib/worker'

type Result = { success: true; data: unknown } | { success: false; error: string }

async function getJwt(): Promise<string | null> {
  const supabase = await createClient()
  const { data } = await supabase.auth.getSession()
  return data.session?.access_token ?? null
}

export async function ensureGeneratedSessions(days = 7): Promise<Result> {
  const jwt = await getJwt()
  if (!jwt) return { success: false, error: 'unauthenticated' }
  try {
    const data = await workerEnsureSessions(jwt, days)
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
    return { success: true, data }
  } catch (e) {
    return { success: false, error: (e as Error).message }
  }
}
