import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'
import { Toaster } from '@/components/ui/sonner'
import { OnboardingWizard, type WizardInitial } from './_components/onboarding-wizard'
import type { Step } from '@/lib/onboarding/steps'

interface ProfileRow {
  first_name: string | null
  dob: string | null
  sex: 'M' | 'F' | 'X' | null
  city: string | null
  country: string | null
  ftp_watts: number | null
  vma_kmh: number | null
  fc_max_bpm: number | null
  css_per_100m_s: number | null
  hours_per_week: number | null
  available_days: string[] | null
  sports_strengths: { swim?: number; bike?: number; run?: number } | null
  garmin_synced_at: string | null
  onboarding_completed_at: string | null
  consent_data_processing: boolean
}

interface RaceRow {
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

function computeInitialStep(profile: ProfileRow | null, race: RaceRow | null): Step {
  if (!profile?.first_name || !profile.dob || !profile.sex) return 'perso'
  if (!race) return 'race'
  const hasPerf =
    profile.ftp_watts !== null ||
    profile.vma_kmh !== null ||
    profile.fc_max_bpm !== null ||
    profile.css_per_100m_s !== null
  if (!hasPerf && !profile.garmin_synced_at) return 'perf'
  if (!profile.hours_per_week) return 'dispo'
  return 'dispo'
}

export default async function OnboardingPage() {
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (!user) redirect('/login')

  const [{ data: profile }, { data: race }] = await Promise.all([
    supabase.from('athlete_profiles').select('*').eq('user_id', user.id).single<ProfileRow>(),
    supabase
      .from('race_goals')
      .select('race_date, discipline, name, location, target_time_seconds, legs')
      .eq('user_id', user.id)
      .eq('is_primary', true)
      .maybeSingle<RaceRow>(),
  ])

  if (profile?.onboarding_completed_at) redirect('/profile')

  const initialStep = computeInitialStep(profile, race)

  const initial: WizardInitial = {
    perso:
      profile?.first_name && profile.dob && profile.sex
        ? {
            first_name: profile.first_name,
            dob: profile.dob,
            sex: profile.sex,
            city: profile.city ?? '',
            country: profile.country ?? '',
            consent_data_processing: profile.consent_data_processing as true,
          }
        : null,
    race: race
      ? {
          race_date: race.race_date,
          discipline: race.discipline,
          name: race.name ?? undefined,
          location: race.location ?? undefined,
          target_time_seconds: race.target_time_seconds ?? undefined,
          legs: race.legs,
        }
      : null,
    perf: {
      ftp_watts: profile?.ftp_watts ?? undefined,
      vma_kmh: profile?.vma_kmh ?? undefined,
      fc_max_bpm: profile?.fc_max_bpm ?? undefined,
      css_per_100m_s: profile?.css_per_100m_s ?? undefined,
      garmin_synced_at: profile?.garmin_synced_at ?? null,
    },
    dispo: {
      available_days: profile?.available_days?.filter(
        (d): d is 'mon' | 'tue' | 'wed' | 'thu' | 'fri' | 'sat' | 'sun' =>
          ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'].includes(d)
      ),
      hours_per_week: profile?.hours_per_week ?? undefined,
      sports_strengths:
        profile?.sports_strengths?.swim &&
        profile.sports_strengths.bike &&
        profile.sports_strengths.run
          ? {
              swim: profile.sports_strengths.swim,
              bike: profile.sports_strengths.bike,
              run: profile.sports_strengths.run,
            }
          : undefined,
    },
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Bienvenue {profile?.first_name ?? ''}</h1>
        <p className="text-muted-foreground text-sm">
          Quelques infos pour générer ton plan d&apos;entraînement. ~5 minutes.
        </p>
      </header>
      <OnboardingWizard initial={initial} initialStep={initialStep} />
      <Toaster />
    </div>
  )
}
