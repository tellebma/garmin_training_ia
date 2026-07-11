import { getServerEnv } from './env'

export type ConnectResult =
  | { status: 'connected' }
  | { status: 'mfa_required'; challenge_id: string }
  | { status: 'invalid_credentials'; retry_after_seconds?: number }
  | { status: 'rate_limited'; retry_after_seconds?: number }
  | { status: 'garmin_error'; error_id: string; type: string }
  | { status: 'unexpected_error'; error_id: string; type: string }

export type MfaResult =
  | { status: 'connected' }
  | { status: 'invalid_code'; retry_after_seconds?: number }
  | { status: 'challenge_expired' }
  | { status: 'challenge_user_mismatch' }
  | { status: 'rate_limited'; retry_after_seconds?: number }
  | { status: 'garmin_error'; error_id: string; type: string }
  | { status: 'unexpected_error'; error_id: string; type: string }

export type ProfileSyncResult =
  | { status: 'ok'; fetched: { ftp_watts?: number; vma_kmh?: number; fc_max_bpm?: number } }
  | { status: 'no_credentials' }
  | { status: 'auth_failed' }
  | { status: 'rate_limited' }
  | { status: 'garmin_error'; type: string }
  | { status: 'unexpected_error'; error_id: string; type: string }

export async function workerPost<T>(
  path: string,
  body: unknown,
  userJwt: string,
  timeoutMs = 60_000
): Promise<T> {
  const { WORKER_URL } = getServerEnv()
  const res = await fetch(`${WORKER_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${userJwt}`,
    },
    body: JSON.stringify(body),
    cache: 'no-store',
    signal: AbortSignal.timeout(timeoutMs),
  })

  // 401 is auth failure — still throw so Server Action knows
  if (res.status === 401) {
    const text = await res.text()
    throw new Error(`Worker rejected JWT (401): ${text}`)
  }

  // All other statuses: try to parse JSON body so we don't lose context.
  try {
    return (await res.json()) as T
  } catch {
    const text = await res.text().catch(() => '<unreadable>')
    throw new Error(`Worker returned ${String(res.status)} with non-JSON body: ${text}`)
  }
}

export type EnsureSessionsResult =
  | { generated_count: number; failed_count: number; skipped_count: number }
  | { status: 'rate_limited'; retry_after_seconds: number }
  | { status: 'unexpected_error'; error_id: string; type: string }

export type RegenerateSessionResult =
  | { status: 'ok'; workout: unknown }
  | { status: 'session_not_found' }
  | { status: 'rate_limited'; retry_after_seconds: number }
  | { status: 'unexpected_error'; error_id: string; type: string }

export async function workerEnsureSessions(
  jwt: string,
  days: number
): Promise<EnsureSessionsResult> {
  return workerPost<EnsureSessionsResult>('/coach/ensure-sessions', { days }, jwt)
}

export async function workerRegenerateSession(
  jwt: string,
  sessionId: string
): Promise<RegenerateSessionResult> {
  return workerPost<RegenerateSessionResult>(`/coach/regenerate-session/${sessionId}`, {}, jwt)
}

export async function workerDailyBriefing(jwt: string): Promise<unknown> {
  return workerPost<unknown>('/coach/daily-briefing', {}, jwt)
}

export type SyncTriggerResult =
  | { status: 'started' }
  | { status: 'cooldown'; retry_after_seconds: number }
  | { status: 'no_credentials' }
  | { status: 'invalid_trigger' }
  | { status: 'unexpected_error'; error_id: string; type: string }

export async function workerTriggerSync(
  jwt: string,
  trigger: 'auto' | 'manual'
): Promise<SyncTriggerResult> {
  return workerPost<SyncTriggerResult>(`/garmin/sync?trigger=${trigger}`, {}, jwt)
}

export type StravaConnectResult =
  | { status: 'connected' }
  | { status: 'strava_auth_error' }
  | { status: 'rate_limited' }
  | { status: 'unexpected_error'; error_id: string; type: string }

export type StravaDisconnectResult =
  | { status: 'disconnected' }
  | { status: 'not_connected' }
  | { status: 'unexpected_error'; error_id: string; type: string }

export async function workerStravaConnect(jwt: string, code: string): Promise<StravaConnectResult> {
  return workerPost<StravaConnectResult>('/strava/connect', { code }, jwt)
}

export async function workerStravaDisconnect(jwt: string): Promise<StravaDisconnectResult> {
  return workerPost<StravaDisconnectResult>('/strava/disconnect', {}, jwt)
}
