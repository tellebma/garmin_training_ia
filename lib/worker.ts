import { getServerEnv } from './env'

export type ConnectResult =
  | { status: 'connected' }
  | { status: 'mfa_required'; challenge_id: string }
  | { status: 'invalid_credentials' }

export type MfaResult =
  | { status: 'connected' }
  | { status: 'invalid_code' }
  | { status: 'challenge_expired' }
  | { status: 'challenge_user_mismatch' }

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
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Worker error ${String(res.status)}: ${text}`)
  }
  return res.json() as Promise<T>
}
