import { Suspense } from 'react'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import { ArrowLeft, Flame, Gauge, HeartPulse, Mountain, Route, Timer, Zap } from 'lucide-react'
import { ActivityDetailSkeleton } from '../../_components/skeletons/activity-detail-skeleton'
import { ActivityComparisonChart } from '../../_components/charts/activity-comparison-chart'
import { ActivitySamplesChart } from '../../_components/charts/activity-samples-chart'
import { ChartCard } from '../../_components/chart-card'
import { MetricTile } from '../../_components/metric-tile'
import { SPORT_LABEL } from '../../_components/sport-icon'
import {
  buildNextSessionAdjustment,
  buildActivityCoachAnalysis,
  summarizeActivitySamples,
  summarizeSimilarActivities,
  type ActivityDetail,
} from '@/lib/coach/activity-analysis'
import { fetchAllActivitySamples } from '@/lib/activities/activity-samples'
import {
  formatDistanceFromMeters,
  formatDuration,
  formatTSS,
  formatSpeedForSport,
} from '@/lib/dashboard/format'
import { requireOnboarded } from '@/lib/onboarding/guard'
import { createClient } from '@/lib/supabase/server'
import { cn } from '@/lib/utils'
import type { ActivityFeedbackDto, PlannedSession, Sport } from '@/lib/dashboard/types'
import { ActivityRouteMapLazy } from '../../_components/maps/activity-route-map-lazy'
import { ActivityFeedbackForm } from './activity-feedback-form'

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
  const speedMs = activity.distance_m / activity.duration_s
  const sport: Sport = knownSport(activity.sport) ? activity.sport : 'bike'
  return formatSpeedForSport(sport, speedMs)
}

function formatNumber(value: number | null | undefined, suffix = ''): string {
  if (value === null || value === undefined) return '—'
  return `${String(Math.round(value))}${suffix}`
}

function formatDecimal(value: number | null | undefined, suffix = ''): string {
  if (value === null || value === undefined) return '—'
  return `${value.toFixed(1)}${suffix}`
}

function formatSignedDecimal(value: number | null | undefined, suffix = ''): string {
  if (value === null || value === undefined) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(1)}${suffix}`
}

function toneClass(tone: 'positive' | 'watch' | 'risk'): string {
  if (tone === 'risk') return 'border-red-500/30 bg-red-500/5'
  if (tone === 'watch') return 'border-amber-500/30 bg-amber-500/5'
  return 'border-emerald-500/30 bg-emerald-500/5'
}

function cardioDriftText(signal: 'stable' | 'watch' | 'risk' | 'insufficient'): string {
  if (signal === 'insufficient') return 'Pas assez de points cardio pour conclure proprement.'
  if (signal === 'stable') return 'La relation cardio / vitesse reste stable sur cette activité.'
  return 'La seconde moitié coûte plus cher en cardio : c’est un signal à gérer sur les prochaines séances.'
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

      <Suspense fallback={<ActivityDetailSkeleton />}>
        <ActivityDetailBody userId={userId} activity={activity} />
      </Suspense>
    </div>
  )
}

async function ActivityDetailBody({
  userId,
  activity,
}: {
  readonly userId: string
  readonly activity: ActivityDetail
}) {
  const supabase = await createClient()
  const activityDate = isoDate(activity.start_time)
  const ninetyDaysAgo = new Date(
    new Date(activity.start_time).getTime() - 90 * 86_400_000
  ).toISOString()

  const [plannedRes, similarRes, samples, profileRes, upcomingRes, feedbackRes] = await Promise.all(
    [
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
      fetchAllActivitySamples(supabase, {
        userId,
        garminActivityId: activity.garmin_activity_id,
      }),
      supabase.from('athlete_profiles').select('fc_max_bpm').eq('user_id', userId).maybeSingle(),
      supabase
        .from('planned_sessions')
        .select(
          'id, date, sport, session_type, target_duration_s, target_tss, target_elevation_gain_m, phase, week_offset, notes'
        )
        .eq('user_id', userId)
        .gt('date', activityDate)
        .order('date', { ascending: true })
        .limit(3),
      supabase
        .from('activity_feedback')
        .select(
          'activity_id, rpe, fatigue, soreness, pain, mood, perceived_difficulty, pain_area, comment, updated_at'
        )
        .eq('user_id', userId)
        .eq('activity_id', activity.id)
        .maybeSingle(),
    ]
  )

  const plannedSession: PlannedSession | null = plannedRes.data ?? null
  const similarActivities: ActivityDetail[] = similarRes.data ?? []
  const gpsSampleCount = samples.filter(
    (s) => typeof s.latitude === 'number' && typeof s.longitude === 'number'
  ).length
  const upcomingSessions: PlannedSession[] = upcomingRes.data ?? []
  const activityFeedback: ActivityFeedbackDto | null = feedbackRes.data ?? null
  const profileData = profileRes.data as { fc_max_bpm?: unknown } | null
  const profileFcMax = typeof profileData?.fc_max_bpm === 'number' ? profileData.fc_max_bpm : null
  const fcMax: number | null = profileFcMax ?? activity.hr_max ?? null
  const similar = summarizeSimilarActivities(similarActivities)
  const analysis = buildActivityCoachAnalysis({ activity, plannedSession, similar })
  const sampleSummary = samples.length > 0 ? summarizeActivitySamples(samples, fcMax) : null
  const nextSessionAdjustment = buildNextSessionAdjustment(sampleSummary, upcomingSessions)

  return (
    <>
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

      <ActivityFeedbackForm
        activityId={activity.id}
        durationSeconds={activity.duration_s}
        initialFeedback={activityFeedback}
      />

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

      {gpsSampleCount >= 2 && (
        <ChartCard
          title="Trace GPS"
          description="Parcours de l'activité d'après les données Garmin."
        >
          <ActivityRouteMapLazy samples={samples} />
        </ChartCard>
      )}

      {samples.length > 0 && (
        <ChartCard
          title="Courbes d'activité"
          description="Fréquence cardiaque, altitude, puissance, cadence et allure selon les données Garmin disponibles."
        >
          <ActivitySamplesChart
            data={samples}
            sport={knownSport(activity.sport) ? activity.sport : 'bike'}
          />
        </ChartCard>
      )}

      {sampleSummary && (
        <section className="grid gap-4 xl:grid-cols-[1fr_1.35fr_0.9fr]">
          <div className="bg-card rounded-lg border p-4">
            <h2 className="text-sm font-semibold">Zones cardio</h2>
            <div className="mt-4 space-y-3">
              {sampleSummary.hrZones.map((zone) => (
                <div key={zone.zone}>
                  <div className="mb-1 flex items-center justify-between text-xs">
                    <span className="font-medium">{zone.zone}</span>
                    <span className="text-muted-foreground">
                      {zone.label} · {zone.percent.toFixed(1)}%
                    </span>
                  </div>
                  <div className="bg-muted h-2 overflow-hidden rounded">
                    <div
                      className="bg-primary h-full rounded"
                      style={{ width: `${String(Math.min(100, zone.percent))}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
            <div className="text-muted-foreground mt-4 space-y-2 text-sm">
              {sampleSummary.insights.map((insight) => (
                <p key={insight}>{insight}</p>
              ))}
            </div>
          </div>

          <div className="bg-card rounded-lg border p-4">
            <h2 className="text-sm font-semibold">Montée / plat / descente</h2>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-muted-foreground text-xs uppercase">
                  <tr>
                    <th className="py-2 pr-3">Terrain</th>
                    <th className="py-2 pr-3">Distance</th>
                    <th className="py-2 pr-3">Pente</th>
                    <th className="py-2 pr-3">FC</th>
                    <th className="py-2 pr-3">Vitesse</th>
                    <th className="py-2">Régularité</th>
                  </tr>
                </thead>
                <tbody>
                  {sampleSummary.terrain.map((segment) => (
                    <tr key={segment.terrain} className="border-border/60 border-t">
                      <td className="py-2 pr-3 font-medium">{segment.terrain}</td>
                      <td className="py-2 pr-3">{formatDistanceFromMeters(segment.distance_m)}</td>
                      <td className="py-2 pr-3">{formatDecimal(segment.avg_grade_pct, '%')}</td>
                      <td className="py-2 pr-3">{formatNumber(segment.avg_hr_bpm, ' bpm')}</td>
                      <td className="py-2 pr-3">
                        {formatSpeedForSport(
                          knownSport(activity.sport) ? activity.sport : 'bike',
                          segment.avg_speed_kmh != null ? segment.avg_speed_kmh / 3.6 : null
                        )}
                      </td>
                      <td className="py-2">{formatDecimal(segment.speed_variability_pct, '%')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="text-muted-foreground mt-4 space-y-2 text-sm">
              {sampleSummary.recommendations.map((recommendation) => (
                <p key={recommendation}>{recommendation}</p>
              ))}
            </div>
          </div>

          <div className="bg-card rounded-lg border p-4">
            <h2 className="text-sm font-semibold">Dérive cardio</h2>
            <dl className="text-muted-foreground mt-3 grid grid-cols-2 gap-3 text-sm">
              <div>
                <dt className="text-xs uppercase">FC début</dt>
                <dd className="text-foreground">
                  {formatNumber(sampleSummary.cardioDrift.first_half_avg_hr_bpm, ' bpm')}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase">FC fin</dt>
                <dd className="text-foreground">
                  {formatNumber(sampleSummary.cardioDrift.second_half_avg_hr_bpm, ' bpm')}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase">Écart FC</dt>
                <dd className="text-foreground">
                  {formatSignedDecimal(sampleSummary.cardioDrift.drift_bpm, ' bpm')}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase">Vitesse</dt>
                <dd className="text-foreground">
                  {formatSignedDecimal(sampleSummary.cardioDrift.speed_change_pct, '%')}
                </dd>
              </div>
            </dl>
            <p className="text-muted-foreground mt-4 text-sm">
              {cardioDriftText(sampleSummary.cardioDrift.signal)}
            </p>
          </div>
        </section>
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

      <section className="bg-card rounded-lg border p-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
              Impact sur la suite
            </p>
            <h2 className="mt-1 text-sm font-semibold">{nextSessionAdjustment.title}</h2>
            <p className="text-muted-foreground mt-2 text-sm">{nextSessionAdjustment.rationale}</p>
          </div>
          {nextSessionAdjustment.targetSession && (
            <div className="bg-muted rounded-md px-3 py-2 text-sm md:min-w-48">
              <p className="font-medium">
                {new Date(nextSessionAdjustment.targetSession.date).toLocaleDateString('fr-FR', {
                  weekday: 'short',
                  day: 'numeric',
                  month: 'short',
                })}
              </p>
              <p className="text-muted-foreground">
                {knownSport(nextSessionAdjustment.targetSession.sport)
                  ? SPORT_LABEL[nextSessionAdjustment.targetSession.sport]
                  : nextSessionAdjustment.targetSession.sport}{' '}
                · {nextSessionAdjustment.targetSession.session_type}
              </p>
            </div>
          )}
        </div>
        <p className="mt-4 text-sm">{nextSessionAdjustment.recommendation}</p>
      </section>
    </>
  )
}
