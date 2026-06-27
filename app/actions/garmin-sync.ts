'use server'

import { createClient } from '@/lib/supabase/server'
import { workerTriggerSync, type SyncTriggerResult } from '@/lib/worker'

async function getUserJwt(): Promise<string> {
  const supabase = await createClient()
  const {
    data: { session },
  } = await supabase.auth.getSession()
  if (!session) {
    throw new Error('Not authenticated')
  }
  return session.access_token
}

export async function triggerGarminSync(trigger: 'auto' | 'manual'): Promise<SyncTriggerResult> {
  const jwt = await getUserJwt()
  return workerTriggerSync(jwt, trigger)
}
