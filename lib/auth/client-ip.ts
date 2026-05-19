import { headers } from 'next/headers'

/**
 * Resolve client IP from request headers, Vercel-aware.
 * Order: x-vercel-forwarded-for > x-real-ip > x-forwarded-for > 'unknown'.
 *
 * Vercel normalizes x-vercel-forwarded-for at the edge (un-spoofable when behind Vercel).
 * x-forwarded-for left-most is the standard but spoofable outside Vercel.
 *
 * In production, callers must refuse 'unknown' (failure-closed — see ipIsTrusted).
 */
export async function clientIp(): Promise<string> {
  const h = await headers()
  const vercel = h.get('x-vercel-forwarded-for')
  if (vercel) return (vercel.split(',')[0] ?? vercel).trim()
  const real = h.get('x-real-ip')
  if (real) return real
  const fwd = h.get('x-forwarded-for')
  if (fwd) return (fwd.split(',')[0] ?? fwd).trim()
  return 'unknown'
}

/**
 * Returns true if the IP can be trusted for rate limiting.
 * In production, 'unknown' is refused (failure-closed).
 */
export function ipIsTrusted(ip: string): boolean {
  return !(ip === 'unknown' && process.env.NODE_ENV === 'production')
}
