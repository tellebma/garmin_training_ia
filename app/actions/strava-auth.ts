'use server'

import { createClient } from '@/lib/supabase/server'
import {
  workerStravaConnect,
  workerStravaDisconnect,
  type StravaConnectResult,
  type StravaDisconnectResult,
} from '@/lib/worker'

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

export async function connectStrava(code: string): Promise<StravaConnectResult> {
  const jwt = await getUserJwt()
  return workerStravaConnect(jwt, code)
}

export async function disconnectStrava(): Promise<StravaDisconnectResult> {
  const jwt = await getUserJwt()
  return workerStravaDisconnect(jwt)
}
