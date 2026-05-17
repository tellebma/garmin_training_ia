'use server'

import { createClient } from '@/lib/supabase/server'
import { workerPost, type ConnectResult, type MfaResult } from '@/lib/worker'

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

export async function connectGarmin(email: string, password: string): Promise<ConnectResult> {
  const jwt = await getUserJwt()
  return workerPost<ConnectResult>('/garmin/connect', { email, password }, jwt)
}

export async function submitGarminMfa(challenge_id: string, code: string): Promise<MfaResult> {
  const jwt = await getUserJwt()
  return workerPost<MfaResult>('/garmin/mfa', { challenge_id, code }, jwt)
}
