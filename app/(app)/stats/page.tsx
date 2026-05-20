// app/(app)/stats/page.tsx
import { Activity as ActivityIcon, HeartPulse, Moon } from 'lucide-react'
import { requireOnboarded } from '@/lib/onboarding/guard'
import { createClient } from '@/lib/supabase/server'
import { ChartCard } from '../_components/chart-card'
import { EmptyState } from '../_components/empty-state'
import { BanisterChart } from '../_components/charts/banister-chart'
import { HrvTrendChart } from '../_components/charts/hrv-trend-chart'
import { SleepTrendChart } from '../_components/charts/sleep-trend-chart'
import { WeeklyVolumeChart } from '../_components/charts/weekly-volume-chart'
import { computeWeeklyVolume } from '@/lib/dashboard/weekly-volume'
import type { ActivityRowDto, BanisterPoint, HrvDto, SleepDto } from '@/lib/dashboard/types'

// Stats sont dérivées des syncs Garmin (cron daily 5h UTC). Cache 1h
// pour éviter de re-frapper Supabase à chaque ouverture / navigation.
export const revalidate = 3600

export default async function StatsPage() {
  const userId = await requireOnboarded()
  const supabase = await createClient()

  // Server component runs once per request — Date.now() is deterministic here.
  /* eslint-disable react-hooks/purity */
  const ninetyDaysAgo = new Date(Date.now() - 90 * 86_400_000).toISOString().slice(0, 10)
  const twelveWeeksAgo = new Date(Date.now() - 84 * 86_400_000).toISOString().slice(0, 10)
  const thirtyDaysAgo = new Date(Date.now() - 30 * 86_400_000).toISOString().slice(0, 10)
  /* eslint-enable react-hooks/purity */

  const [banisterRes, activitiesRes, hrvRes, sleepRes] = await Promise.all([
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
      .gte('start_time', twelveWeeksAgo),
    supabase
      .from('hrv')
      .select('date, hrv_rmssd, hrv_status, hrv_weekly_avg')
      .eq('user_id', userId)
      .gte('date', thirtyDaysAgo)
      .order('date', { ascending: true }),
    supabase
      .from('sleep')
      .select('date, sleep_score, sleep_duration_s')
      .eq('user_id', userId)
      .gte('date', thirtyDaysAgo)
      .order('date', { ascending: true }),
  ])

  const banister = (banisterRes.data ?? []) as BanisterPoint[]
  const activities = (activitiesRes.data ?? []) as ActivityRowDto[]
  const hrv = (hrvRes.data ?? []) as HrvDto[]
  const sleep = (sleepRes.data ?? []) as SleepDto[]
  const weeklyVolume = computeWeeklyVolume(activities, 12)

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Statistiques</h1>
      </header>

      <ChartCard title="Forme (90 jours)" description="CTL fitness · ATL fatigue · TSB forme">
        {banister.length >= 14 ? (
          <BanisterChart data={banister} />
        ) : (
          <EmptyState
            icon={ActivityIcon}
            title="Pas encore d'historique"
            description="Reviens dans 1-2 semaines."
          />
        )}
      </ChartCard>

      <ChartCard title="Volume hebdomadaire" description="12 dernières semaines (min)">
        {activities.length > 0 ? (
          <WeeklyVolumeChart data={weeklyVolume} />
        ) : (
          <EmptyState
            icon={ActivityIcon}
            title="Pas encore d'activités"
            description="Connecte Garmin et attends le prochain sync."
          />
        )}
      </ChartCard>

      <ChartCard title="HRV (30 jours)" description="Variabilité cardiaque nocturne">
        {hrv.length > 0 ? (
          <HrvTrendChart data={hrv} />
        ) : (
          <EmptyState
            icon={HeartPulse}
            title="HRV non disponible"
            description="Ta montre Garmin ne renvoie pas de HRV."
          />
        )}
      </ChartCard>

      <ChartCard title="Sommeil (30 jours)" description="Score Garmin (objectif ≥ 80)">
        {sleep.length > 0 ? (
          <SleepTrendChart data={sleep} />
        ) : (
          <EmptyState
            icon={Moon}
            title="Sommeil non disponible"
            description="Aucune donnée sleep synchronisée."
          />
        )}
      </ChartCard>
    </div>
  )
}
