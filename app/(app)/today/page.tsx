// app/(app)/today/page.tsx
import {
  Activity as ActivityIcon,
  BatteryCharging,
  CalendarOff,
  HeartPulse,
  Moon,
} from 'lucide-react'
import { requireOnboarded } from '@/lib/onboarding/guard'
import { createClient } from '@/lib/supabase/server'
import { ChartCard } from '../_components/chart-card'
import { EmptyState } from '../_components/empty-state'
import { GarminStatusBanner } from '../_components/garmin-status-banner'
import { MetricTile } from '../_components/metric-tile'
import { PhaseBadge } from '../_components/phase-badge'
import { SessionCard } from '../_components/session-card'
import { ActivityRow } from '../_components/activity-row'
import { BanisterChart } from '../_components/charts/banister-chart'
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

function renderSessionSection(session: PlannedSession | null): React.ReactNode {
  if (session && session.session_type !== 'rest') {
    return <SessionCard session={session} />
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

export default async function TodayPage() {
  const userId = await requireOnboarded()
  const supabase = await createClient()
  const now = new Date()
  const today = isoDate(now)
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
        'id, date, sport, session_type, target_duration_s, target_tss, phase, week_offset, notes'
      )
      .eq('user_id', userId)
      .eq('date', today)
      .maybeSingle(),
    supabase
      .from('daily_metrics')
      .select('date, body_battery_high, body_battery_low, stress_avg, resting_hr')
      .eq('user_id', userId)
      .eq('date', today)
      .maybeSingle(),
    supabase
      .from('sleep')
      .select('date, score, total_seconds')
      .eq('user_id', userId)
      .eq('date', today)
      .maybeSingle(),
    supabase
      .from('hrv')
      .select('date, last_night_avg, baseline_low, baseline_high')
      .eq('user_id', userId)
      .eq('date', today)
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
        'id, garmin_activity_id, start_time, sport, duration_s, distance_km, elevation_gain_m, tss, hr_avg'
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
      .select('last_sync_status, last_sync_error_message')
      .eq('user_id', userId)
      .maybeSingle(),
  ])

  // eslint-disable-next-line @typescript-eslint/no-unnecessary-type-assertion
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

  const sleepValue = sleep?.score ? String(sleep.score) : '—'
  const hrvValue = hrv?.last_night_avg
    ? `${String(Math.round(Number(hrv.last_night_avg)))} ms`
    : '—'
  const batteryValue = daily?.body_battery_high ? String(daily.body_battery_high) : '—'

  return (
    <div className="space-y-6">
      <GarminStatusBanner status={garminSyncStatus} errorMessage={garminSyncError} />
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
          <ActivityRow activity={lastActivity} />
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
