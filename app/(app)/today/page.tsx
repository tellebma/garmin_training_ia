// app/(app)/today/page.tsx
import { Suspense } from 'react'
import Link from 'next/link'
import {
  Activity as ActivityIcon,
  BatteryCharging,
  CalendarOff,
  HeartPulse,
  Moon,
} from 'lucide-react'
import { getDailyBriefing } from '@/app/actions/briefing'
import { ensureGeneratedSessions } from '@/app/actions/sessions'
import { requireOnboarded } from '@/lib/onboarding/guard'
import { createClient } from '@/lib/supabase/server'
import { workoutToMarkdown } from '@/lib/coach/session-templates'
import type { Sport as CoachSport } from '@/lib/coach/session-templates'
import type { Workout } from '@/lib/coach/workout-types'
import { BriefingCard } from '../_components/briefing-card'
import { ChartCard } from '../_components/chart-card'
import { EmptyState } from '../_components/empty-state'
import { GarminStatusBanner } from '../_components/garmin-status-banner'
import { MetricTile } from '../_components/metric-tile'
import { PhaseBadge } from '../_components/phase-badge'
import { SessionCard } from '../_components/session-card'
import { ActivityRow } from '../_components/activity-row'
import { BanisterChart } from '../_components/charts/banister-chart'
import { SyncTimingsCard } from '../_components/sync-timings-card'
import { BriefingCardSkeleton } from '../_components/skeletons/briefing-card-skeleton'
import type { ActivityRowDto, BanisterPoint, PlannedSession, RaceGoal } from '@/lib/dashboard/types'

export const revalidate = 0

function daysUntil(iso: string): number {
  const target = new Date(iso)
  const now = new Date()
  return Math.round((target.setHours(0, 0, 0, 0) - now.setHours(0, 0, 0, 0)) / 86_400_000)
}

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10)
}

function renderWorkoutMarkdown(session: PlannedSession): React.ReactNode {
  if (session.workout) {
    return (
      <pre className="rounded-md border p-4 text-sm whitespace-pre-wrap">
        {workoutToMarkdown(
          session.workout as Workout,
          session.sport as CoachSport,
          session.session_type
        )}
      </pre>
    )
  }
  return (
    <div className="text-muted-foreground text-sm italic">
      Structure de séance en cours de génération… recharge la page dans quelques secondes.
    </div>
  )
}

function renderSessionSection(session: PlannedSession | null): React.ReactNode {
  if (session && session.session_type !== 'rest') {
    return (
      <div className="space-y-3">
        <SessionCard session={session} />
        {renderWorkoutMarkdown(session)}
      </div>
    )
  }
  if (session?.session_type === 'rest') {
    return (
      <EmptyState
        icon={CalendarOff}
        title="Jour de repos"
        description="Profite-en pour récupérer."
      />
    )
  }
  return (
    <EmptyState
      icon={CalendarOff}
      title="Pas de plan actif"
      description="Le plan est régénéré dimanche soir 22h UTC."
    />
  )
}

async function BriefingLoader() {
  const result = await getDailyBriefing().catch(() => null)
  const briefing = result?.success ? result.briefing : null
  if (!briefing) return null
  return <BriefingCard briefing={briefing} />
}

export default async function TodayPage() {
  const userId = await requireOnboarded()

  // Fire-and-forget — don't block the render. If the worker is down,
  // we still display whatever workout already exists.
  void ensureGeneratedSessions(7).catch(() => undefined)

  const supabase = await createClient()
  const now = new Date()
  const today = isoDate(now)
  // Note: pour sleep/hrv/daily_metrics, on lit la DERNIERE entrée (order by date)
  // plutôt que today exactement, parce que Garmin date typiquement la nuit J-1
  // -> on aurait toujours "—" en consultant /today le lendemain matin.
  const ninetyDaysAgo = isoDate(new Date(now.getTime() - 90 * 86_400_000))

  const [
    sessionRes,
    dailyRes,
    sleepRes,
    hrvRes,
    banisterRes,
    lastActivityRes,
    raceRes,
    garminCredsRes,
  ] = await Promise.all([
    supabase
      .from('planned_sessions')
      .select(
        'id, date, sport, session_type, target_duration_s, target_tss, target_elevation_gain_m, phase, week_offset, notes, workout, workout_generated_at, plan_id, training_plans!inner(status)'
      )
      .eq('user_id', userId)
      .eq('date', today)
      .eq('training_plans.status', 'active')
      .order('created_at', { ascending: false })
      .limit(1)
      .maybeSingle(),
    supabase
      .from('daily_metrics')
      .select('date, body_battery_high, body_battery_low, stress_avg, resting_hr')
      .eq('user_id', userId)
      .order('date', { ascending: false })
      .limit(1)
      .maybeSingle(),
    supabase
      .from('sleep')
      .select('date, sleep_score, sleep_duration_s')
      .eq('user_id', userId)
      .order('date', { ascending: false })
      .limit(1)
      .maybeSingle(),
    supabase
      .from('hrv')
      .select('date, hrv_rmssd, hrv_status, hrv_weekly_avg')
      .eq('user_id', userId)
      .order('date', { ascending: false })
      .limit(1)
      .maybeSingle(),
    supabase
      .from('daily_banister_state')
      .select('date, ctl, atl, tsb')
      .eq('user_id', userId)
      .gte('date', ninetyDaysAgo)
      .order('date', { ascending: true }),
    supabase
      .from('activities')
      .select(
        'id, garmin_activity_id, start_time, sport, duration_s, distance_m, elevation_gain_m, tss, hr_avg'
      )
      .eq('user_id', userId)
      .order('start_time', { ascending: false })
      .limit(1)
      .maybeSingle(),
    supabase
      .from('race_goals')
      .select('race_date, name, discipline')
      .eq('user_id', userId)
      .eq('is_primary', true)
      .maybeSingle(),
    supabase
      .from('garmin_credentials')
      .select(
        'last_sync_status, last_sync_error_message, last_sleep_sync_at, last_activities_sync_at, last_profile_sync_at'
      )
      .eq('user_id', userId)
      .maybeSingle(),
  ])

  const session = sessionRes.data as PlannedSession | null
  const daily = dailyRes.data
  const sleep = sleepRes.data
  const hrv = hrvRes.data
  const banister = (banisterRes.data ?? []) as BanisterPoint[]
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-type-assertion
  const lastActivity = lastActivityRes.data as ActivityRowDto | null
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-type-assertion
  const race = raceRes.data as RaceGoal | null
  const garminSyncStatus = (garminCredsRes.data?.last_sync_status ?? null) as string | null
  const garminSyncError = (garminCredsRes.data?.last_sync_error_message ?? null) as string | null
  const lastSleepSyncAt = (garminCredsRes.data?.last_sleep_sync_at ?? null) as string | null
  const lastActivitiesSyncAt = (garminCredsRes.data?.last_activities_sync_at ?? null) as
    | string
    | null
  const lastProfileSyncAt = (garminCredsRes.data?.last_profile_sync_at ?? null) as string | null

  const sleepValue = sleep?.sleep_score ? String(sleep.sleep_score) : '—'
  const hrvValue = hrv?.hrv_rmssd ? `${String(Math.round(Number(hrv.hrv_rmssd)))} ms` : '—'
  const batteryValue = daily?.body_battery_high ? String(daily.body_battery_high) : '—'

  return (
    <div className="space-y-6">
      <GarminStatusBanner
        status={garminSyncStatus}
        errorMessage={garminSyncError}
        lastActivitiesSyncAt={lastActivitiesSyncAt}
      />
      <header className="flex items-start justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold">Aujourd&rsquo;hui</h1>
          <p className="text-muted-foreground text-sm">
            {now.toLocaleDateString('fr-FR', {
              weekday: 'long',
              day: 'numeric',
              month: 'long',
            })}
          </p>
        </div>
        {race && (
          <div className="text-right">
            <p className="text-muted-foreground text-xs">{race.name ?? 'Course'}</p>
            <p className="text-foreground text-sm font-semibold">
              J-{String(daysUntil(race.race_date))}
            </p>
          </div>
        )}
      </header>

      <SyncTimingsCard
        lastSleepSyncAt={lastSleepSyncAt}
        lastActivitiesSyncAt={lastActivitiesSyncAt}
        lastProfileSyncAt={lastProfileSyncAt}
      />

      <Suspense fallback={<BriefingCardSkeleton />}>
        <BriefingLoader />
      </Suspense>

      <section>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-foreground text-sm font-semibold tracking-wide uppercase">
            Séance du jour
          </h2>
          {session && <PhaseBadge phase={session.phase} />}
        </div>
        {renderSessionSection(session)}
      </section>

      <section className="grid grid-cols-3 gap-2">
        <MetricTile icon={Moon} label="Sommeil" value={sleepValue} />
        <MetricTile icon={HeartPulse} label="HRV" value={hrvValue} />
        <MetricTile icon={BatteryCharging} label="Battery" value={batteryValue} />
      </section>

      <ChartCard title="Forme (Banister 90j)" description="CTL fitness · ATL fatigue · TSB forme">
        {banister.length >= 14 ? (
          <BanisterChart data={banister} />
        ) : (
          <EmptyState
            icon={ActivityIcon}
            title="Pas encore d'historique"
            description="Reviens dans 1-2 semaines après quelques activités."
          />
        )}
      </ChartCard>

      <section>
        <h2 className="text-foreground mb-2 text-sm font-semibold tracking-wide uppercase">
          Dernière activité
        </h2>
        {lastActivity ? (
          <Link href={`/history/${lastActivity.id}`} className="block">
            <ActivityRow activity={lastActivity} />
          </Link>
        ) : (
          <EmptyState
            icon={ActivityIcon}
            title="Aucune activité synchronisée"
            description="Connecte Garmin et attends le prochain sync (05:00 UTC)."
          />
        )}
      </section>
    </div>
  )
}
