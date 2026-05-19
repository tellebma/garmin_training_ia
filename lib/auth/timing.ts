/**
 * Sleep until Date.now() reaches `targetMs`. No-op if already past target.
 * Used to enforce a constant-floor execution time on auth Server Actions,
 * defeating timing-based account enumeration (audit C2).
 */
export async function sleepUntil(targetMs: number): Promise<void> {
  const remaining = targetMs - Date.now()
  if (remaining > 0) {
    await new Promise((resolve) => setTimeout(resolve, remaining))
  }
}

/** Minimum execution time (ms) for any auth-sensitive Server Action. */
export const AUTH_MIN_DURATION_MS = 800
