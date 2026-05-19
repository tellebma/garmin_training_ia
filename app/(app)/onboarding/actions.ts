'use server'

import { revalidatePath } from 'next/cache'
import { redirect } from 'next/navigation'
import { z } from 'zod'
import { createClient } from '@/lib/supabase/server'
import {
  personSchema,
  raceSchema,
  perfSchema,
  dispoSchema,
  DISPO_DEFAULTS,
  computeTotals,
  type PersonInput,
  type RaceInput,
  type PerfInput,
  type DispoInput,
} from '@/lib/onboarding/schemas'
import { nextStep, type Step } from '@/lib/onboarding/steps'
import { workerPost, type ProfileSyncResult } from '@/lib/worker'

const ONBOARDING_PATH = '/onboarding'

export type StepResult =
  | { success: true; nextStep: Step | null }
  | { success: false; errors: Partial<Record<string, string[]>> }
  | { success: false; error: 'save_failed' | 'unauthenticated' }

async function requireUserId(): Promise<string | { success: false; error: 'unauthenticated' }> {
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (!user) return { success: false, error: 'unauthenticated' }
  return user.id
}

export async function saveStepPerso(input: PersonInput): Promise<StepResult> {
  const parsed = personSchema.safeParse(input)
  if (!parsed.success) {
    return { success: false, errors: z.flattenError(parsed.error).fieldErrors }
  }
  const userIdOrErr = await requireUserId()
  if (typeof userIdOrErr !== 'string') return userIdOrErr

  const supabase = await createClient()
  // La row existe forcément via le trigger handle_new_user (créée à la signup).
  // On fait un UPDATE direct — pas d'upsert qui demanderait aussi la policy INSERT.
  const { error } = await supabase
    .from('athlete_profiles')
    .update({
      first_name: parsed.data.first_name,
      dob: parsed.data.dob,
      sex: parsed.data.sex,
      city: parsed.data.city ?? null,
      country: parsed.data.country ?? null,
      consent_data_processing: parsed.data.consent_data_processing,
      consent_signed_at: new Date().toISOString(),
    })
    .eq('user_id', userIdOrErr)
  if (error) return { success: false, error: 'save_failed' }

  revalidatePath(ONBOARDING_PATH)
  return { success: true, nextStep: nextStep('perso') }
}

export async function saveStepRace(input: RaceInput): Promise<StepResult> {
  const parsed = raceSchema.safeParse(input)
  if (!parsed.success) {
    return { success: false, errors: z.flattenError(parsed.error).fieldErrors }
  }
  const userIdOrErr = await requireUserId()
  if (typeof userIdOrErr !== 'string') return userIdOrErr

  const supabase = await createClient()

  // Defense in depth — UI computes totals live, but Server Action recompute
  // to avoid trusting client-supplied totals.
  const { total_distance_km, total_elevation_gain_m } = computeTotals(parsed.data.legs)

  const { data: existing } = await supabase
    .from('race_goals')
    .select('id')
    .eq('user_id', userIdOrErr)
    .eq('is_primary', true)
    .maybeSingle()

  const payload = {
    user_id: userIdOrErr,
    race_date: parsed.data.race_date,
    discipline: parsed.data.discipline,
    name: parsed.data.name ?? null,
    location: parsed.data.location ?? null,
    target_time_seconds: parsed.data.target_time_seconds ?? null,
    legs: parsed.data.legs,
    total_distance_km,
    total_elevation_gain_m,
    is_primary: true,
  }

  const { error } = existing
    ? await supabase.from('race_goals').update(payload).eq('id', existing.id)
    : await supabase.from('race_goals').insert(payload)

  if (error) return { success: false, error: 'save_failed' }

  revalidatePath(ONBOARDING_PATH)
  return { success: true, nextStep: nextStep('race') }
}

export async function saveStepPerf(input: PerfInput): Promise<StepResult> {
  const parsed = perfSchema.safeParse(input)
  if (!parsed.success) {
    return { success: false, errors: z.flattenError(parsed.error).fieldErrors }
  }
  const userIdOrErr = await requireUserId()
  if (typeof userIdOrErr !== 'string') return userIdOrErr

  const supabase = await createClient()
  const patch: Record<string, number | null> = {}
  if (parsed.data.ftp_watts !== undefined) patch.ftp_watts = parsed.data.ftp_watts
  if (parsed.data.vma_kmh !== undefined) patch.vma_kmh = parsed.data.vma_kmh
  if (parsed.data.fc_max_bpm !== undefined) patch.fc_max_bpm = parsed.data.fc_max_bpm

  if (Object.keys(patch).length > 0) {
    const { error } = await supabase
      .from('athlete_profiles')
      .update(patch)
      .eq('user_id', userIdOrErr)
    if (error) return { success: false, error: 'save_failed' }
  }

  revalidatePath(ONBOARDING_PATH)
  return { success: true, nextStep: nextStep('perf') }
}

export async function syncGarminProfile(): Promise<ProfileSyncResult> {
  const userIdOrErr = await requireUserId()
  if (typeof userIdOrErr !== 'string') {
    return { status: 'unexpected_error', error_id: '0', type: 'unauthenticated' }
  }
  const supabase = await createClient()
  const {
    data: { session },
  } = await supabase.auth.getSession()
  if (!session) {
    return { status: 'unexpected_error', error_id: '0', type: 'no_session' }
  }
  const result = await workerPost<ProfileSyncResult>(
    '/garmin/profile-sync',
    {},
    session.access_token
  )
  revalidatePath(ONBOARDING_PATH)
  revalidatePath('/profile')
  return result
}

export async function saveStepDispo(input: DispoInput): Promise<StepResult> {
  const parsed = dispoSchema.safeParse(input)
  if (!parsed.success) {
    return { success: false, errors: z.flattenError(parsed.error).fieldErrors }
  }
  const userIdOrErr = await requireUserId()
  if (typeof userIdOrErr !== 'string') return userIdOrErr

  const supabase = await createClient()
  const patch = {
    available_days: parsed.data.available_days ?? DISPO_DEFAULTS.available_days,
    hours_per_week: parsed.data.hours_per_week ?? DISPO_DEFAULTS.hours_per_week,
    sports_strengths: parsed.data.sports_strengths ?? DISPO_DEFAULTS.sports_strengths,
  }

  const { error } = await supabase.from('athlete_profiles').update(patch).eq('user_id', userIdOrErr)
  if (error) return { success: false, error: 'save_failed' }

  revalidatePath(ONBOARDING_PATH)
  return { success: true, nextStep: nextStep('dispo') }
}

export async function finalizeOnboarding(): Promise<void> {
  const userIdOrErr = await requireUserId()
  if (typeof userIdOrErr !== 'string') redirect('/login')

  const supabase = await createClient()

  // Defense in depth : verify Perso (first_name+dob+sex+consent) AND Race
  // minimum BEFORE flagging onboarding complete. Prevents corrupted state if
  // the client wizard ever lets the user skip a required step.
  const [{ data: profile }, { data: race }] = await Promise.all([
    supabase
      .from('athlete_profiles')
      .select('first_name, dob, sex, consent_data_processing')
      .eq('user_id', userIdOrErr)
      .single<{
        first_name: string | null
        dob: string | null
        sex: 'M' | 'F' | 'X' | null
        consent_data_processing: boolean
      }>(),
    supabase
      .from('race_goals')
      .select('id')
      .eq('user_id', userIdOrErr)
      .eq('is_primary', true)
      .maybeSingle(),
  ])

  if (
    !profile?.first_name ||
    !profile.dob ||
    !profile.sex ||
    !profile.consent_data_processing ||
    !race
  ) {
    // Not enough data — redirect back to /onboarding so the wizard re-opens
    // at the first incomplete step (computed by page.tsx).
    redirect('/onboarding')
  }

  await supabase
    .from('athlete_profiles')
    .update({ onboarding_completed_at: new Date().toISOString() })
    .eq('user_id', userIdOrErr)

  revalidatePath('/profile')
  redirect('/profile?onboarded=1')
}
