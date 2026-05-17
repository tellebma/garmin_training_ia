import { getServerEnv } from './env'

export type ConnectResult =
  | { status: 'connected' }
  | { status: 'mfa_required'; challenge_id: string }
  | { status: 'invalid_credentials' }
  | { status: 'rate_limited' }
  | { status: 'garmin_error'; detail: string }
  | { status: 'unexpected_error'; detail: string; type: string; traceback?: string }

export type MfaResult =
  | { status: 'connected' }
  | { status: 'invalid_code' }
  | { status: 'challenge_expired' }
  | { status: 'challenge_user_mismatch' }
  | { status: 'rate_limited' }
  | { status: 'garmin_error'; detail: string }
  | { status: 'unexpected_error'; detail: string; type: string; traceback?: string }

export async function workerPost<T>(path: string, body: unknown, userJwt: string): Promise<T> {
  const { WORKER_URL } = getServerEnv()
  const res = await fetch(`${WORKER_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${userJwt}`,
    },
    body: JSON.stringify(body),
    cache: 'no-store',
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
