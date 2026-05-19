'use server'

import { headers } from 'next/headers'
import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'
import { clientIp, ipIsTrusted } from '@/lib/auth/client-ip'
import { sleepUntil, AUTH_MIN_DURATION_MS } from '@/lib/auth/timing'
import { z } from 'zod'
import {
  registerSchema,
  loginSchema,
  forgotPasswordSchema,
  setPasswordSchema,
  type RegisterInput,
  type LoginInput,
  type ForgotPasswordInput,
  type SetPasswordInput,
} from '@/lib/auth/schemas'

// =========================================
// Common types
// =========================================
export type ActionError =
  | 'rate_limited'
  | 'email_not_allowed'
  | 'invalid_credentials'
  | 'ip_unresolved'
  | 'already_set'
  | 'unauthenticated'
  | 'save_failed'

export type ActionResult =
  | { success: true }
  | { success: false; error: ActionError }
  | { success: false; errors: Record<string, string[]> }

// =========================================
// Helpers
// =========================================
async function userAgent(): Promise<string> {
  return (await headers()).get('user-agent') ?? ''
}

async function originFromHeaders(): Promise<string> {
  const h = await headers()
  const proto = h.get('x-forwarded-proto') ?? 'https'
  const host = h.get('host') ?? 'garmin-training-ia.vercel.app'
  return `${proto}://${host}`
}

// =========================================
// registerWithMagicLink
// =========================================
export async function registerWithMagicLink(input: RegisterInput): Promise<ActionResult> {
  const t0 = Date.now()

  // 1. Zod parse
  const parsed = registerSchema.safeParse(input)
  if (!parsed.success) {
    await sleepUntil(t0 + AUTH_MIN_DURATION_MS)
    return { success: false, errors: z.flattenError(parsed.error).fieldErrors }
  }
  const email = parsed.data.email

  // 2. clientIp + failure-closed in prod (I2)
  const ip = await clientIp()
  if (!ipIsTrusted(ip)) {
    await sleepUntil(t0 + AUTH_MIN_DURATION_MS)
    return { success: false, error: 'ip_unresolved' }
  }

  const supabase = await createClient()
  const ua = await userAgent()

  // 3. Rate limit (I1)
  const rateResult = await supabase.rpc('check_and_log_auth_rate_limit', {
    p_ip: ip,
    p_action: 'register',
    p_max_count: 3,
    p_window_seconds: 3600,
  })
  if (!rateResult.data) {
    await sleepUntil(t0 + AUTH_MIN_DURATION_MS)
    return { success: false, error: 'rate_limited' }
  }

  // 4. is_email_allowed
  const allowedResult = await supabase.rpc('is_email_allowed', { p_email: email })
  if (!allowedResult.data) {
    await sleepUntil(t0 + AUTH_MIN_DURATION_MS)
    return { success: false, error: 'email_not_allowed' }
  }

  // 5. email_needs_signup (I3) — n'envoie l'OTP que si user pas déjà actif
  const signupResult = await supabase.rpc('email_needs_signup', { p_email: email })
  if (!signupResult.data) {
    // Email allowlisté mais déjà actif → réponse success-générique SANS OTP (anti-spam)
    await sleepUntil(t0 + AUTH_MIN_DURATION_MS)
    return { success: true }
  }

  // 6. Envoi OTP
  const origin = await originFromHeaders()
  const { error: otpError } = await supabase.auth.signInWithOtp({
    email,
    options: {
      shouldCreateUser: true,
      emailRedirectTo: `${origin}/auth/callback?next=/auth/set-password`,
    },
  })

  // 7. Audit log (I5)
  if (!otpError) {
    await supabase.rpc('log_auth_event', {
      p_user_id: null,
      p_event_type: 'register_initiated',
      p_ip: ip,
      p_user_agent: ua,
      p_email: email,
    })
  }

  // 8. Anti-timing floor (C2)
  await sleepUntil(t0 + AUTH_MIN_DURATION_MS)
  return { success: true }
}

// =========================================
// login
// =========================================
export async function login(input: LoginInput): Promise<ActionResult> {
  const t0 = Date.now()

  const parsed = loginSchema.safeParse(input)
  if (!parsed.success) {
    await sleepUntil(t0 + AUTH_MIN_DURATION_MS)
    return { success: false, errors: z.flattenError(parsed.error).fieldErrors }
  }
  const { email, password } = parsed.data

  const ip = await clientIp()
  if (!ipIsTrusted(ip)) {
    await sleepUntil(t0 + AUTH_MIN_DURATION_MS)
    return { success: false, error: 'ip_unresolved' }
  }

  const supabase = await createClient()
  const ua = await userAgent()

  // Rate limit : 10/15min
  const loginRateResult = await supabase.rpc('check_and_log_auth_rate_limit', {
    p_ip: ip,
    p_action: 'login',
    p_max_count: 10,
    p_window_seconds: 900,
  })
  if (!loginRateResult.data) {
    await sleepUntil(t0 + AUTH_MIN_DURATION_MS)
    return { success: false, error: 'rate_limited' }
  }

  const { error: signInError, data: signInData } = await supabase.auth.signInWithPassword({
    email,
    password,
  })

  if (signInError) {
    await supabase.rpc('log_auth_event', {
      p_user_id: null,
      p_event_type: 'login_failure',
      p_ip: ip,
      p_user_agent: ua,
      p_email: email,
    })
    await sleepUntil(t0 + AUTH_MIN_DURATION_MS)
    return { success: false, error: 'invalid_credentials' }
  }

  await supabase.rpc('log_auth_event', {
    p_user_id: signInData.user.id,
    p_event_type: 'login_success',
    p_ip: ip,
    p_user_agent: ua,
    p_email: email,
  })

  await sleepUntil(t0 + AUTH_MIN_DURATION_MS)
  return { success: true }
}

// =========================================
// requestPasswordReset (forgot password)
// Always returns success-générique (no email enum leak).
// =========================================
export async function requestPasswordReset(input: ForgotPasswordInput): Promise<ActionResult> {
  const t0 = Date.now()

  const parsed = forgotPasswordSchema.safeParse(input)
  if (!parsed.success) {
    await sleepUntil(t0 + AUTH_MIN_DURATION_MS)
    return { success: true } // success-générique
  }
  const email = parsed.data.email

  const ip = await clientIp()
  if (!ipIsTrusted(ip)) {
    await sleepUntil(t0 + AUTH_MIN_DURATION_MS)
    return { success: false, error: 'ip_unresolved' }
  }

  const supabase = await createClient()
  const ua = await userAgent()

  // Rate limit : 3/h
  const forgotRateResult = await supabase.rpc('check_and_log_auth_rate_limit', {
    p_ip: ip,
    p_action: 'forgot_password',
    p_max_count: 3,
    p_window_seconds: 3600,
  })
  if (!forgotRateResult.data) {
    await sleepUntil(t0 + AUTH_MIN_DURATION_MS)
    return { success: true } // always-success even when rate-limited (anti-leak)
  }

  const origin = await originFromHeaders()
  const { error: resetError } = await supabase.auth.resetPasswordForEmail(email, {
    redirectTo: `${origin}/auth/callback?next=/auth/reset-password`,
  })

  if (!resetError) {
    await supabase.rpc('log_auth_event', {
      p_user_id: null,
      p_event_type: 'password_reset_requested',
      p_ip: ip,
      p_user_agent: ua,
      p_email: email,
    })
  }

  await sleepUntil(t0 + AUTH_MIN_DURATION_MS)
  return { success: true }
}

// =========================================
// setInitialPassword
// Called from /auth/set-password (1ère connexion via magic link register).
// I4 guard : refuse if password_set === true already (anti session-theft → reset lockout).
// =========================================
export async function setInitialPassword(input: SetPasswordInput): Promise<ActionResult> {
  const parsed = setPasswordSchema.safeParse(input)
  if (!parsed.success) {
    return { success: false, errors: z.flattenError(parsed.error).fieldErrors }
  }
  const { password } = parsed.data

  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (!user) {
    return { success: false, error: 'unauthenticated' }
  }

  // I4 — guard : refuse si password_set déjà true (cette action ne sert que pour la 1ère fois)
  const { data: profile } = await supabase
    .from('athlete_profiles')
    .select('password_set')
    .eq('user_id', user.id)
    .single<{ password_set: boolean }>()

  if (profile?.password_set === true) {
    return { success: false, error: 'already_set' }
  }

  const { error: updateError } = await supabase.auth.updateUser({ password })
  if (updateError) return { success: false, error: 'save_failed' }

  const { error: flagError } = await supabase
    .from('athlete_profiles')
    .update({ password_set: true })
    .eq('user_id', user.id)
  if (flagError) return { success: false, error: 'save_failed' }

  // Audit
  const ip = await clientIp()
  const ua = await userAgent()
  await supabase.rpc('log_auth_event', {
    p_user_id: user.id,
    p_event_type: 'password_set',
    p_ip: ip,
    p_user_agent: ua,
    p_email: user.email ?? '',
  })

  redirect('/onboarding')
}

// =========================================
// setPasswordAfterReset
// Called from /auth/reset-password (after clicking the email reset link).
// Updates password + sets password_set=true (covers migration legacy users).
// =========================================
export async function setPasswordAfterReset(input: SetPasswordInput): Promise<ActionResult> {
  const parsed = setPasswordSchema.safeParse(input)
  if (!parsed.success) {
    return { success: false, errors: z.flattenError(parsed.error).fieldErrors }
  }
  const { password } = parsed.data

  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (!user) {
    return { success: false, error: 'unauthenticated' }
  }

  const { error: updateError } = await supabase.auth.updateUser({ password })
  if (updateError) return { success: false, error: 'save_failed' }

  // Idempotent : si déjà true, ne change rien
  const { error: flagError } = await supabase
    .from('athlete_profiles')
    .update({ password_set: true })
    .eq('user_id', user.id)
  if (flagError) return { success: false, error: 'save_failed' }

  const ip = await clientIp()
  const ua = await userAgent()
  await supabase.rpc('log_auth_event', {
    p_user_id: user.id,
    p_event_type: 'password_reset_completed',
    p_ip: ip,
    p_user_agent: ua,
    p_email: user.email ?? '',
  })

  redirect('/today')
}
