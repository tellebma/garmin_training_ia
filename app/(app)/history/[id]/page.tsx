import Link from 'next/link'
import { notFound } from 'next/navigation'
import { ArrowLeft, Flame, Gauge, HeartPulse, Mountain, Route, Timer, Zap } from 'lucide-react'
import { ActivityComparisonChart } from '../../_components/charts/activity-comparison-chart'
import { ActivitySamplesChart } from '../../_components/charts/activity-samples-chart'
import { ChartCard } from '../../_components/chart-card'
import { MetricTile } from '../../_components/metric-tile'
import { SPORT_LABEL } from '../../_components/sport-icon'
import {
  buildActivityCoachAnalysis,
  summarizeSimilarActivities,
  type ActivityDetail,
  type ActivitySample,
} from '@/lib/coach/activity-analysis'
import { formatDistanceFromMeters, formatDuration, formatTSS } from '@/lib/dashboard/format'
import { requireOnboarded } from '@/lib/onboarding/guard'
import { createClient } from '@/lib/supabase/server'
import { cn } from '@/lib/utils'
import type { PlannedSession, Sport } from '@/lib/dashboard/types'

export const revalidate = 300

interface ActivityDetailPageProps {
  readonly params: Promise<{ readonly id: string }>
}

function knownSport(s: string): s is Sport {
  return ['swim', 'bike', 'run', 'brick', 'rest', 'race'].includes(s)
}

function isoDate(iso: string): string {
  return new Date(iso).toISOString().slice(0, 10)
}

function formatPace(secondsPerKm: number | null | undefined): string {
  if (!secondsPerKm || secondsPerKm <= 0) return '—'
  const minutes = Math.floor(secondsPerKm / 60)
  const seconds = Math.round(secondsPerKm % 60)
  return `${String(minutes)}:${String(seconds).padStart(2, '0')} /km`
}

function formatSpeed(activity: ActivityDetail): string {
  if (!activity.distance_m || !activity.duration_s || activity.duration_s <= 0) return '—'
  const kmh = activity.distance_m / 1000 / (activity.duration_s / 3600)
  return `${kmh.toFixed(1)} km/h`
}

function formatNumber(value: number | null | undefined, suffix = ''): string {
  if (value === null || value === undefined) return '—'
  return `${String(Math.round(value))}${suffix}`
}

function toneClass(tone: 'positive' | 'watch' | 'risk'): string {
  if (tone === 'risk') return 'border-red-500/30 bg-red-500/5'
  if (tone === 'watch') return 'border-amber-500/30 bg-amber-500/5'
  return 'border-emerald-500/30 bg-emerald-500/5'
}

export default async function ActivityDetailPage({ params }: ActivityDetailPageProps) {
  const userId = await requireOnboarded()
  const { id } = await params
  const supabase = await createClient()

  const { data: activityData } = await supabase
    .from('activities')
    .select(
      'id, garmin_activity_id, start_time, sport, duration_s, distance_m, elevation_gain_m, tss, hr_avg, hr_max, power_avg, power_max, pace_avg_s_per_km, calories'
    )
    .eq('user_id', userId)
    .eq('id', id)
    .maybeSingle()

  if (!activityData) notFound()

  const activity: ActivityDetail = activityData
  const activityDate = isoDate(activity.start_time)
  const ninetyDaysAgo = new Date(
    new Date(activity.start_time).getTime() - 90 * 86_400_000
  ).toISOString()

  const [plannedRes, similarRes, samplesRes] = await Promise.all([
    supabase
      .from('planned_sessions')
      .select(
        'id, date, sport, session_type, target_duration_s, target_tss, target_elevation_gain_m, phase, week_offset, notes'
      )
      .eq('user_id', userId)
      .eq('date', activityDate)
      .order('created_at', { ascending: false })
      .limit(1)
      .maybeSingle(),
    supabase
      .from('activities')
      .select(
        'id, garmin_activity_id, start_time, sport, duration_s, distance_m, elevation_gain_m, tss, hr_avg, hr_max, power_avg, power_max, pace_avg_s_per_km, calories'
      )
      .eq('user_id', userId)
      .eq('sport', activity.sport)
      .neq('id', activity.id)
      .gte('start_time', ninetyDaysAgo)
      .order('start_time', { ascending: false })
      .limit(12),
    supabase
      .from('activity_samples')
      .select(
        'sample_index, sample_time, elapsed_s, distance_m, elevation_m, heart_rate_bpm, power_w, cadence_rpm, speed_m_s'
      )
      .eq('user_id', userId)
      .eq('garmin_activity_id', activity.garmin_activity_id)
      .order('sample_index', { ascending: true })
      .limit(2000),
  ])

  const plannedSession: PlannedSession | null = plannedRes.data ?? null
  const similarActivities: ActivityDetail[] = similarRes.data ?? []
  const samples: ActivitySample[] = samplesRes.data ?? []
  const similar = summarizeSimilarActivities(similarActivities)
  const analysis = buildActivityCoachAnalysis({ activity, plannedSession, similar })
  const sportLabel = knownSport(activity.sport) ? SPORT_LABEL[activity.sport] : activity.sport

  return (
    <div className="space-y-6">
      <header className="space-y-3">
        <Link
          href="/history"
          className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs"
        >
          <ArrowLeft size={14} />
          Historique
        </Link>
        <div>
          <p className="text-muted-foreground text-sm">
            {new Date(activity.start_time).toLocaleDateString('fr-FR', {
              weekday: 'long',
              day: 'numeric',
              month: 'long',
              year: 'numeric',
            })}
          </p>
          <h1 className="text-2xl font-semibold">{sportLabel}</h1>
        </div>
      </header>

      <section className={cn('rounded-lg border p-4', toneClass(analysis.tone))}>
        <p className="text-sm font-semibold">{analysis.title}</p>
        <p className="text-muted-foreground mt-1 text-sm">{analysis.summary}</p>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div>
            <h2 className="text-xs font-semibold tracking-wide uppercase">
              Ce que le coach retient
            </h2>
            <ul className="text-muted-foreground mt-2 space-y-2 text-sm">
              {analysis.insights.map((insight) => (
                <li key={insight}>{insight}</li>
              ))}
            </ul>
          </div>
          <div>
            <h2 className="text-xs font-semibold tracking-wide uppercase">Prochaines séances</h2>
            <ul className="text-muted-foreground mt-2 space-y-2 text-sm">
              {analysis.recommendations.map((recommendation) => (
                <li key={recommendation}>{recommendation}</li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MetricTile icon={Timer} label="Durée" value={formatDuration(activity.duration_s)} />
        <MetricTile
          icon={Route}
          label="Distance"
          value={formatDistanceFromMeters(activity.distance_m)}
        />
        <MetricTile
          icon={Mountain}
          label="Dénivelé"
          value={formatNumber(activity.elevation_gain_m, ' m')}
        />
        <MetricTile icon={Flame} label="Charge" value={formatTSS(activity.tss)} />
        <MetricTile
          icon={HeartPulse}
          label="FC moyenne"
          value={formatNumber(activity.hr_avg, ' bpm')}
        />
        <MetricTile
          icon={HeartPulse}
          label="FC max"
          value={formatNumber(activity.hr_max, ' bpm')}
        />
        <MetricTile icon={Zap} label="Puissance" value={formatNumber(activity.power_avg, ' W')} />
        <MetricTile
          icon={Gauge}
          label="Allure / vitesse"
          value={
            activity.pace_avg_s_per_km
              ? formatPace(activity.pace_avg_s_per_km)
              : formatSpeed(activity)
          }
        />
      </section>

      <ChartCard
        title="Réalisé vs prévu"
        description={`Comparaison avec la séance planifiée et ${String(similar.count)} activité(s) similaire(s).`}
      >
        <ActivityComparisonChart data={analysis.chartData} />
      </ChartCard>

      {samples.length > 0 && (
        <ChartCard
          title="Courbes d'activité"
          description="Fréquence cardiaque, altitude, puissance, cadence et allure selon les données Garmin disponibles."
        >
          <ActivitySamplesChart data={samples} />
        </ChartCard>
      )}

      <section className="grid gap-4 md:grid-cols-2">
        <div className="bg-card rounded-lg border p-4">
          <h2 className="text-sm font-semibold">Séance prévue</h2>
          {plannedSession ? (
            <dl className="text-muted-foreground mt-3 grid grid-cols-2 gap-3 text-sm">
              <div>
                <dt className="text-xs uppercase">Sport</dt>
                <dd className="text-foreground">
                  {knownSport(plannedSession.sport)
                    ? SPORT_LABEL[plannedSession.sport]
                    : plannedSession.sport}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase">Type</dt>
                <dd className="text-foreground">{plannedSession.session_type}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase">Durée</dt>
                <dd className="text-foreground">
                  {formatDuration(plannedSession.target_duration_s)}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase">Charge</dt>
                <dd className="text-foreground">{formatTSS(plannedSession.target_tss)}</dd>
              </div>
            </dl>
          ) : (
            <p className="text-muted-foreground mt-2 text-sm">
              Aucune séance planifiée trouvée ce jour-là.
            </p>
          )}
        </div>
        <div className="bg-card rounded-lg border p-4">
          <h2 className="text-sm font-semibold">Référence récente</h2>
          <dl className="text-muted-foreground mt-3 grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-xs uppercase">Activités</dt>
              <dd className="text-foreground">{similar.count}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase">Charge moy.</dt>
              <dd className="text-foreground">{formatTSS(similar.avg_tss)}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase">Durée moy.</dt>
              <dd className="text-foreground">{formatDuration(similar.avg_duration_s)}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase">FC moy.</dt>
              <dd className="text-foreground">{formatNumber(similar.avg_hr_avg, ' bpm')}</dd>
            </div>
          </dl>
        </div>
      </section>
    </div>
  )
}
