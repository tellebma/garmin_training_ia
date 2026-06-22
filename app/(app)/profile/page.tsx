import { Suspense } from 'react'
import Link from 'next/link'
import { SignOutButton } from '@/components/auth/sign-out-button'
import { Button } from '@/components/ui/button'
import { requireOnboarded } from '@/lib/onboarding/guard'
import { createClient } from '@/lib/supabase/server'
import {
  CoachAdjustmentDecisionsSection,
  type CoachAdjustmentDecisionRow,
} from './_components/coach-adjustment-decisions-section'
import { DisciplineLevelsLoader } from './_components/discipline-levels-loader'
import { DisciplineLevelsSkeleton } from './_components/discipline-levels-skeleton'
import { PersoEditForm } from './_components/perso-edit-form'
import { RaceEditForm } from './_components/race-edit-form'
import { PerfEditForm } from './_components/perf-edit-form'
import { DispoEditForm } from './_components/dispo-edit-form'
import type { PersonInput, RaceInput, PerfInput, DispoInput } from '@/lib/onboarding/schemas'

interface AthleteProfileRow {
  first_name: string | null
  dob: string | null
  sex: string | null
  city: string | null
  country: string | null
  consent_data_processing: boolean | null
  ftp_watts: number | null
  vma_kmh: number | null
  fc_max_bpm: number | null
  garmin_synced_at: string | null
  available_days: string[] | null
  hours_per_week: number | null
  sports_strengths: { swim: number; bike: number; run: number } | null
}

interface RaceGoalRow {
  race_date: string
  discipline: 'triathlon' | 'duathlon' | 'aquathlon' | 'run' | 'bike' | 'swim' | 'autre'
  name: string | null
  location: string | null
  target_time_seconds: number | null
  legs: {
    order: number
    discipline: 'swim' | 'bike' | 'run'
    distance_km: number
    elevation_gain_m: number
  }[]
}

interface GarminCredentialsRow {
  last_sync_at: string | null
  last_sync_status: string | null
  initial_sync_completed_at: string | null
  token_refresh_failed_at: string | null
  updated_at: string
}

function formatDateTime(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' })
}

export default async function ProfilePage() {
  const userId = await requireOnboarded()

  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()

  const [{ data: profile }, { data: race }, { data: garmin }, { data: adjustmentDecisions }] =
    await Promise.all([
      supabase
        .from('athlete_profiles')
        .select(
          'first_name, dob, sex, city, country, consent_data_processing, ftp_watts, vma_kmh, fc_max_bpm, garmin_synced_at, available_days, hours_per_week, sports_strengths'
        )
        .eq('user_id', userId)
        .single<AthleteProfileRow>(),
      supabase
        .from('race_goals')
        .select('race_date, discipline, name, location, target_time_seconds, legs')
        .eq('user_id', userId)
        .eq('is_primary', true)
        .maybeSingle<RaceGoalRow>(),
      supabase
        .from('garmin_credentials')
        .select(
          'last_sync_at, last_sync_status, initial_sync_completed_at, token_refresh_failed_at, updated_at'
        )
        .eq('user_id', userId)
        .maybeSingle<GarminCredentialsRow>(),
      supabase
        .from('coach_adjustment_decisions')
        .select(
          'id, planned_session_id, original_session_type, suggested_session_type, decision, source, created_at, planned_sessions(date, sport, session_type)'
        )
        .eq('user_id', userId)
        .order('created_at', { ascending: false })
        .limit(10)
        .overrideTypes<CoachAdjustmentDecisionRow[], { merge: false }>(),
    ])

  const garminConnected = garmin !== null
  const garminAuthStale = garmin !== null && garmin.token_refresh_failed_at !== null

  // Build typed initial props for edit forms
  const persoInitial: PersonInput = {
    first_name: profile?.first_name ?? '',
    dob: profile?.dob ?? '',
    sex: (profile?.sex ?? 'M') as 'M' | 'F' | 'X',
    city: profile?.city ?? undefined,
    country: profile?.country ?? undefined,
    consent_data_processing: profile?.consent_data_processing ?? false,
  }

  const raceInitial: RaceInput | null = race
    ? {
        race_date: race.race_date,
        discipline: race.discipline,
        name: race.name ?? undefined,
        location: race.location ?? undefined,
        target_time_seconds: race.target_time_seconds ?? undefined,
        legs: race.legs,
      }
    : null

  const perfInitial: PerfInput & { garmin_synced_at: string | null } = {
    ftp_watts: profile?.ftp_watts ?? undefined,
    vma_kmh: profile?.vma_kmh ?? undefined,
    fc_max_bpm: profile?.fc_max_bpm ?? undefined,
    garmin_synced_at: profile?.garmin_synced_at ?? null,
  }

  const dispoInitial: DispoInput = {
    available_days: profile?.available_days as DispoInput['available_days'],
    hours_per_week: profile?.hours_per_week ?? undefined,
    sports_strengths: profile?.sports_strengths ?? undefined,
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Profil</h1>
        <p className="text-muted-foreground text-sm">{user?.email}</p>
      </header>

      {/* Garmin Connect section */}
      <section className="space-y-3 rounded-lg border p-6">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">Garmin Connect</h2>
          {garminConnected && !garminAuthStale && (
            <span className="rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-600 dark:text-emerald-400">
              Connecté
            </span>
          )}
          {garminAuthStale && (
            <span className="rounded-full bg-amber-500/10 px-3 py-1 text-xs font-medium text-amber-600 dark:text-amber-400">
              Token expiré
            </span>
          )}
        </div>

        {!garminConnected && (
          <>
            <p className="text-muted-foreground text-sm">
              Connecte ton compte Garmin pour synchroniser tes activités et métriques.
            </p>
            <Button asChild variant="outline">
              <Link href="/profile/garmin">Connecter Garmin</Link>
            </Button>
          </>
        )}

        {garminConnected && (
          <>
            <dl className="text-muted-foreground grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
              <dt>Connecté le</dt>
              <dd className="text-foreground">{formatDateTime(garmin.updated_at)}</dd>
              <dt>Backfill 90 j</dt>
              <dd className="text-foreground">
                {garmin.initial_sync_completed_at
                  ? `terminé le ${formatDateTime(garmin.initial_sync_completed_at)}`
                  : 'en attente (cron 05:00 UTC)'}
              </dd>
              <dt>Dernier sync</dt>
              <dd className="text-foreground">{formatDateTime(garmin.last_sync_at)}</dd>
              <dt>Statut sync</dt>
              <dd className="text-foreground">{garmin.last_sync_status ?? '—'}</dd>
            </dl>
            <Button asChild variant="outline">
              <Link href="/profile/garmin">Reconnecter</Link>
            </Button>
          </>
        )}
      </section>

      {/* Editable sections */}
      <PersoEditForm initial={persoInitial} />
      <RaceEditForm initial={raceInitial} />
      <PerfEditForm initial={perfInitial} />
      <DispoEditForm initial={dispoInitial} />
      <Suspense fallback={<DisciplineLevelsSkeleton />}>
        <DisciplineLevelsLoader />
      </Suspense>
      <CoachAdjustmentDecisionsSection decisions={adjustmentDecisions ?? []} />

      <SignOutButton />
    </div>
  )
}
