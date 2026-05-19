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
  const { error } = await supabase.from('athlete_profiles').upsert(
    {
      user_id: userIdOrErr,
      first_name: parsed.data.first_name,
      dob: parsed.data.dob,
      sex: parsed.data.sex,
      city: parsed.data.city ?? null,
      country: parsed.data.country ?? null,
      consent_data_processing: parsed.data.consent_data_processing,
      consent_signed_at: new Date().toISOString(),
    },
    { onConflict: 'user_id' }
  )
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
  const { data: existing } = await supabase
    .from('race_goals')
    .select('id')
    .eq('user_id', userIdOrErr)
    .eq('is_primary', true)
    .maybeSingle()

  const payload = {
    user_id: userIdOrErr,
    race_date: parsed.data.race_date,
    race_distance: parsed.data.race_distance,
    name: parsed.data.name ?? null,
    location: parsed.data.location ?? null,
    target_time_seconds: parsed.data.target_time_seconds ?? null,
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
  await supabase
    .from('athlete_profiles')
    .update({ onboarding_completed_at: new Date().toISOString() })
    .eq('user_id', userIdOrErr)

  revalidatePath('/profile')
  redirect('/profile?onboarded=1')
}
