// lib/auth/safe-next.ts

/**
 * Whitelist of safe redirect targets (C1 anti-open-redirect).
 * Any other `next` value falls back to '/today'.
 */
const SAFE_NEXT = new Set<string>([
  '/auth/set-password',
  '/auth/reset-password',
  '/today',
  '/onboarding',
  '/profile',
])

/**
 * Returns value if it is in the whitelist, otherwise falls back to '/today'.
 * Exported separately from the route to allow unit testing without Next.js
 * route restrictions.
 */
export function isSafeNext(value: string | null): string {
  if (value && SAFE_NEXT.has(value)) return value
  return '/today'
}
