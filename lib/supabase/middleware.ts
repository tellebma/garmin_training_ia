import { NextResponse, type NextRequest } from 'next/server'
import { env } from '../env'

/**
 * Edge-runtime auth middleware.
 *
 * Why not `@supabase/ssr`?
 * `@supabase/ssr` (and its dependency `@supabase/supabase-js`) bundle code
 * paths that reference Node-only globals like `__dirname`. When those land
 * in the Edge runtime (a V8 isolate, not Node) they crash at request time
 * with `ReferenceError: __dirname is not defined` and Vercel returns 500
 * for every route — including the `/login` page itself, since the
 * middleware runs first.
 *
 * What we do instead: check whether the request carries a Supabase auth
 * cookie. Supabase stores the session in cookies named
 * `sb-<project-ref>-auth-token(.<n>)?`. Their presence is a strong signal
 * that the user has a session — the actual JWT validation happens in
 * server components / route handlers (`lib/supabase/server.ts`), which
 * run on Node and can use `@supabase/ssr` safely.
 *
 * Worst case: a stale or invalid cookie lets the user reach a protected
 * page, where the server-side Supabase client revalidates the token and
 * redirects to `/login` if needed. That is acceptable — middleware is the
 * fast filter, not the source of truth.
 */

// Extract the project ref from `https://<ref>.supabase.co` (or any host).
const PROJECT_REF = (() => {
  try {
    const host = new URL(env.NEXT_PUBLIC_SUPABASE_URL).hostname
    // e.g. "abcd1234.supabase.co" → "abcd1234"
    return host.split('.')[0] ?? ''
  } catch {
    return ''
  }
})()

const AUTH_COOKIE_PREFIX = PROJECT_REF ? `sb-${PROJECT_REF}-auth-token` : 'sb-'

function hasSupabaseSession(request: NextRequest): boolean {
  // `cookies.getAll()` returns every cookie; Supabase may chunk the token
  // across `<prefix>`, `<prefix>.0`, `<prefix>.1`, … Any match counts.
  return request.cookies.getAll().some((c) => c.name.startsWith(AUTH_COOKIE_PREFIX))
}

export function updateSession(request: NextRequest): NextResponse {
  const url = new URL(request.url)
  const isAuthRoute = url.pathname.startsWith('/login') || url.pathname.startsWith('/auth')
  const isPublicAsset =
    url.pathname.startsWith('/_next') ||
    url.pathname.startsWith('/icons') ||
    url.pathname === '/manifest.webmanifest' ||
    url.pathname === '/favicon.ico'

  const isAuthenticated = hasSupabaseSession(request)

  if (!isAuthenticated && !isAuthRoute && !isPublicAsset && url.pathname !== '/') {
    return NextResponse.redirect(new URL('/login', request.url))
  }

  if (isAuthenticated && isAuthRoute) {
    return NextResponse.redirect(new URL('/today', request.url))
  }

  return NextResponse.next({ request })
}
