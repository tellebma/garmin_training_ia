import { Suspense } from 'react'
import Link from 'next/link'
import { Activity as ActivityIcon, HeartPulse, Moon } from 'lucide-react'
import { requireOnboarded } from '@/lib/onboarding/guard'
import { createClient } from '@/lib/supabase/server'
import { CockpitSkeleton } from '../_components/skeletons/cockpit-skeleton'
import { ChartCard } from '../_components/chart-card'
import { EmptyState } from '../_components/empty-state'
import { BanisterChart } from '../_components/charts/banister-chart'
import { HrvTrendChart } from '../_components/charts/hrv-trend-chart'
import { PlannedActualChart } from '../_components/charts/planned-actual-chart'
import { SleepTrendChart } from '../_components/charts/sleep-trend-chart'
import {
  computePerformanceCockpit,
  type CockpitSport,
  type CoachSignalTone,
} from '@/lib/dashboard/performance-cockpit'
import { RecoveryPanel } from '../_components/recovery-panel'
import { mapRecoveryRow } from '@/lib/dashboard/recovery'
import { cn } from '@/lib/utils'
import { RoutesFrequencyMapLazy } from '../_components/maps/routes-frequency-map-lazy'
import { ColsWidget } from '../_components/cols-widget'
import { RacesWidget } from '../_components/races-widget'
import {
  summarizeRaceHistory,
  type RaceActivityRow,
  type RaceGoalRow,
  type RaceResultsRow,
  type RaceSegmentRow,
} from '@/lib/coach/race-analysis'
import { ColsWidgetSkeleton } from '../_components/skeletons/cols-widget-skeleton'
import { computeColsSummary, type ColCrossingRowDto, type ColDto } from '@/lib/dashboard/cols'
import type {
  ActivityFeedbackDto,
  ActivityRowDto,
  BanisterPoint,
  HrvDto,
  PlannedSession,
  SleepDto,
} from '@/lib/dashboard/types'

export const revalidate = 300

const ranges = [7, 28, 90, 'all'] as const
const sports: readonly { value: CockpitSport | 'all'; label: string }[] = [
  { value: 'all', label: 'Tous' },
  { value: 'swim', label: 'Natation' },
  { value: 'bike', label: 'Vélo' },
  { value: 'run', label: 'Course' },
  { value: 'brick', label: 'Enchaîné' },
]

interface Props {
  readonly searchParams: Promise<{ range?: string; sport?: string }>
}

// Intentional discriminated literal union (7 | 28 | 90 | 'all'), not an accidental
// string/number mix.
// eslint-disable-next-line sonarjs/function-return-type
function parseRange(value: string | undefined): (typeof ranges)[number] {
  if (value === 'all') return 'all'
  const parsed = Number(value)
  return ranges.includes(parsed as (typeof ranges)[number]) ? (parsed as 7 | 28 | 90) : 28
}

function rangeLabel(value: (typeof ranges)[number]): string {
  return value === 'all' ? 'Depuis toujours' : `${String(value)} j`
}

function parseSport(value: string | undefined): CockpitSport | 'all' {
  return sports.some((sport) => sport.value === value) ? (value as CockpitSport | 'all') : 'all'
}

function formatMinutes(value: number): string {
  const hours = Math.floor(value / 60)
  const minutes = value % 60
  if (hours === 0) return `${String(minutes)} min`
  if (minutes === 0) return `${String(hours)} h`
  return `${String(hours)} h ${String(minutes).padStart(2, '0')}`
}

function ratioLabel(actual: number, planned: number): string {
  if (planned <= 0) return actual > 0 ? 'Hors plan' : 'Aucune cible'
  return `${String(Math.round((actual / planned) * 100))}% de la cible`
}

function signalClass(tone: CoachSignalTone): string {
  if (tone === 'positive') return 'border-emerald-500/35 bg-emerald-500/5'
  if (tone === 'watch') return 'border-amber-500/40 bg-amber-500/5'
  return 'border-border bg-muted/30'
}

function sportLabel(sport: CockpitSport): string {
  return sports.find((item) => item.value === sport)?.label ?? 'Autre'
}

function filterHref(range: (typeof ranges)[number], sport: CockpitSport | 'all'): string {
  return `/stats?range=${String(range)}&sport=${sport}`
}

function progressPercent(actual: number, planned: number): number {
  if (planned > 0) return Math.min(100, Math.round((actual / planned) * 100))
  return actual > 0 ? 100 : 0
}

async function CockpitBody({
  userId,
  range,
  selectedSport,
}: {
  readonly userId: string
  readonly range: (typeof ranges)[number]
  readonly selectedSport: CockpitSport | 'all'
}) {
  const supabase = await createClient()
  const now = new Date()
  const startDate =
    range === 'all'
      ? '2000-01-01' // sentinel: predates any real data, acts as "no lower bound"
      : new Date(now.getTime() - (range - 1) * 86_400_000).toISOString().slice(0, 10)
  const today = now.toISOString().slice(0, 10)

  const [banisterRes, activitiesRes, plannedRes, feedbackRes, hrvRes, sleepRes, recoveryRes] =
    await Promise.all([
      supabase
        .from('daily_banister_state')
        .select('date, ctl, atl, tsb')
        .eq('user_id', userId)
        .gte('date', startDate)
        .order('date', { ascending: true }),
      supabase
        .from('activities')
        .select(
          'id, garmin_activity_id, start_time, sport, duration_s, distance_m, elevation_gain_m, tss, hr_avg'
        )
        .eq('user_id', userId)
        .gte('start_time', `${startDate}T00:00:00Z`)
        .lte('start_time', `${today}T23:59:59Z`),
      supabase
        .from('planned_sessions')
        .select(
          'id, date, sport, session_type, target_duration_s, target_tss, target_elevation_gain_m, phase, week_offset, notes'
        )
        .eq('user_id', userId)
        .gte('date', startDate)
        .lte('date', today),
      supabase
        .from('activity_feedback')
        .select(
          'activity_id, rpe, fatigue, soreness, pain, mood, perceived_difficulty, pain_area, comment, updated_at'
        )
        .eq('user_id', userId)
        .order('updated_at', { ascending: false })
        .limit(500),
      supabase
        .from('hrv')
        .select('date, hrv_rmssd, hrv_status, hrv_weekly_avg')
        .eq('user_id', userId)
        .gte('date', startDate)
        .order('date', { ascending: true }),
      supabase
        .from('sleep')
        .select('date, sleep_score, sleep_duration_s')
        .eq('user_id', userId)
        .gte('date', startDate)
        .order('date', { ascending: true }),
      supabase.from('recovery_baselines').select('*').eq('user_id', userId).maybeSingle(),
    ])

  const { data: routeRows } = await supabase
    .from('activities')
    .select('route_polyline')
    .eq('user_id', userId)
    .not('route_polyline', 'is', null)

  const polylines = (routeRows ?? []).map((r): unknown => r.route_polyline)
  const hasGpsPoints = polylines.some((p) => Array.isArray(p) && p.length > 0)

  const banister = (banisterRes.data ?? []) as BanisterPoint[]
  const activities = (activitiesRes.data ?? []) as ActivityRowDto[]
  const plannedSessions = (plannedRes.data ?? []) as PlannedSession[]
  const feedback = (feedbackRes.data ?? []) as ActivityFeedbackDto[]
  const hrv = (hrvRes.data ?? []) as HrvDto[]
  const sleep = (sleepRes.data ?? []) as SleepDto[]
  const recoveryRow: unknown = recoveryRes.data
  const cockpit = computePerformanceCockpit({
    activities,
    plannedSessions,
    feedback,
    days: range,
    reference: now,
    sport: selectedSport,
  })
  const adherenceLabel =
    cockpit.adherencePercent === null ? '—' : `${String(cockpit.adherencePercent)}%`
  const rpeLabel = cockpit.averageRpe === null ? '—' : `${cockpit.averageRpe.toFixed(1)}/10`
  const feedbackLabel =
    cockpit.feedbackCount > 0
      ? `${String(cockpit.sessionRpeLoad)} u.a. sur ${String(cockpit.feedbackCount)} séance(s)`
      : 'Ajoute ton RPE après une activité'

  return (
    <>
      <section className={cn('rounded-md border p-4', signalClass(cockpit.coachSignal.tone))}>
        <p className="text-muted-foreground text-xs font-medium uppercase">Lecture coach</p>
        <h2 className="mt-1 text-base font-semibold">{cockpit.coachSignal.title}</h2>
        <p className="text-muted-foreground mt-1 max-w-3xl text-sm">
          {cockpit.coachSignal.summary}
        </p>
      </section>

      <section aria-labelledby="execution-title">
        <div className="flex items-end justify-between gap-4">
          <div>
            <h2 id="execution-title" className="text-lg font-semibold">
              Exécution du plan
            </h2>
            <p className="text-muted-foreground text-sm">
              {range === 'all' ? 'Depuis toujours' : `Du ${startDate} au ${today}`}
            </p>
          </div>
          {cockpit.extraActivities > 0 && (
            <p className="text-muted-foreground text-xs">
              +{cockpit.extraActivities} activité{cockpit.extraActivities > 1 ? 's' : ''} hors plan
            </p>
          )}
        </div>

        <dl className="mt-4 grid border-y sm:grid-cols-2 lg:grid-cols-4">
          <div className="py-4 sm:pr-4 lg:border-r">
            <dt className="text-muted-foreground text-xs uppercase">Assiduité</dt>
            <dd className="mt-1 text-2xl font-semibold">{adherenceLabel}</dd>
            <p className="text-muted-foreground mt-1 text-xs">
              {cockpit.completedSessions}/{cockpit.plannedSessions} séances réalisées
            </p>
          </div>
          <div className="border-t py-4 sm:border-t-0 sm:pl-4 lg:border-r lg:pr-4">
            <dt className="text-muted-foreground text-xs uppercase">Durée</dt>
            <dd className="mt-1 text-2xl font-semibold">
              {formatMinutes(cockpit.actualDurationMin)}
            </dd>
            <p className="text-muted-foreground mt-1 text-xs">
              {ratioLabel(cockpit.actualDurationMin, cockpit.plannedDurationMin)}
            </p>
          </div>
          <div className="border-t py-4 sm:pr-4 lg:border-t-0 lg:border-r lg:pl-4">
            <dt className="text-muted-foreground text-xs uppercase">Charge TSS</dt>
            <dd className="mt-1 text-2xl font-semibold">{cockpit.actualTss}</dd>
            <p className="text-muted-foreground mt-1 text-xs">
              {ratioLabel(cockpit.actualTss, cockpit.plannedTss)}
            </p>
          </div>
          <div className="border-t py-4 sm:pl-4 lg:border-t-0">
            <dt className="text-muted-foreground text-xs uppercase">Ressenti</dt>
            <dd className="mt-1 text-2xl font-semibold">{rpeLabel}</dd>
            <p className="text-muted-foreground mt-1 text-xs">{feedbackLabel}</p>
          </div>
        </dl>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.65fr_1fr]">
        <div>
          <div className="mb-3">
            <h2 className="text-base font-semibold">Durée prévue et réalisée</h2>
            <p className="text-muted-foreground text-sm">Comparaison hebdomadaire en minutes</p>
          </div>
          {cockpit.weekly.some(
            (week) => week.actualDurationMin > 0 || week.plannedDurationMin > 0
          ) ? (
            <PlannedActualChart data={cockpit.weekly} />
          ) : (
            <EmptyState
              icon={ActivityIcon}
              title="Aucune séance sur cette période"
              description="Le cockpit se remplira après la prochaine activité ou mise à jour du plan."
            />
          )}
        </div>

        <div>
          <div className="mb-3">
            <h2 className="text-base font-semibold">Par discipline</h2>
            <p className="text-muted-foreground text-sm">Durée réalisée par rapport à la cible</p>
          </div>
          {cockpit.disciplines.length > 0 ? (
            <div className="divide-y border-y">
              {cockpit.disciplines.map((discipline) => {
                const percent = progressPercent(
                  discipline.actualDurationMin,
                  discipline.plannedDurationMin
                )
                return (
                  <div key={discipline.sport} className="py-3">
                    <div className="flex items-baseline justify-between gap-3 text-sm">
                      <span className="font-medium">{sportLabel(discipline.sport)}</span>
                      <span className="text-muted-foreground text-xs">
                        {formatMinutes(discipline.actualDurationMin)} /{' '}
                        {formatMinutes(discipline.plannedDurationMin)}
                      </span>
                    </div>
                    <div className="bg-muted mt-2 h-1.5 overflow-hidden rounded">
                      <div
                        className="bg-chart-2 h-full rounded"
                        style={{ width: `${String(percent)}%` }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <p className="text-muted-foreground border-y py-6 text-sm">
              Aucune discipline à comparer sur cette période.
            </p>
          )}
        </div>
      </section>

      <section aria-labelledby="load-title" className="space-y-4">
        <div>
          <h2 id="load-title" className="text-lg font-semibold">
            Charge et forme
          </h2>
          <p className="text-muted-foreground text-sm">CTL fitness, ATL fatigue et TSB forme</p>
        </div>
        {banister.length >= 7 ? (
          <BanisterChart data={banister} />
        ) : (
          <EmptyState
            icon={ActivityIcon}
            title="Historique de charge insuffisant"
            description="Quelques jours supplémentaires sont nécessaires pour lire la tendance."
          />
        )}
      </section>

      <section aria-labelledby="recovery-title">
        <div className="mb-4">
          <h2 id="recovery-title" className="text-lg font-semibold">
            Récupération
          </h2>
          <p className="text-muted-foreground text-sm">
            Tendances physiologiques, à interpréter avec ton ressenti
          </p>
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          <ChartCard title="HRV" description={`${String(range)} derniers jours`}>
            {hrv.length > 0 ? (
              <HrvTrendChart data={hrv} />
            ) : (
              <EmptyState
                icon={HeartPulse}
                title="HRV non disponible"
                description="Ta montre ne renvoie pas cette mesure."
              />
            )}
          </ChartCard>
          <ChartCard title="Sommeil" description={`${String(range)} derniers jours`}>
            {sleep.length > 0 ? (
              <SleepTrendChart data={sleep} />
            ) : (
              <EmptyState
                icon={Moon}
                title="Sommeil non disponible"
                description="Aucune donnée de sommeil synchronisée."
              />
            )}
          </ChartCard>
        </div>
        <div className="mt-4">
          <p className="text-muted-foreground mb-3 text-sm">Baselines personnelles sur 28 jours</p>
          <RecoveryPanel data={mapRecoveryRow(recoveryRow)} />
        </div>
      </section>

      {hasGpsPoints && (
        <ChartCard
          title="Où je m'entraîne"
          description="Tes routes, d'autant plus épaisses et claires que tu y passes souvent"
        >
          <RoutesFrequencyMapLazy polylines={polylines} />
        </ChartCard>
      )}
    </>
  )
}

/**
 * Les courses de l'athlète, chargées à part : la lecture de progression d'une
 * épreuve à l'autre ne doit pas retarder le cockpit.
 */
async function RacesWidgetLoader({ userId }: { readonly userId: string }) {
  const supabase = await createClient()

  const [racesRes, activitiesRes, resultsRes] = await Promise.all([
    supabase
      .from('race_goals')
      .select(
        'id, race_date, name, location, discipline, legs, total_distance_km, total_elevation_gain_m, target_time_seconds, prep_start_date'
      )
      .eq('user_id', userId)
      .overrideTypes<RaceGoalRow[], { merge: false }>(),
    supabase
      .from('activities')
      .select(
        'id, garmin_activity_id, start_time, sport, duration_s, distance_m, elevation_gain_m, hr_avg, pace_avg_s_per_km, tss, race_goal_id'
      )
      .eq('user_id', userId)
      .not('race_goal_id', 'is', null)
      .overrideTypes<(RaceActivityRow & { race_goal_id: string })[], { merge: false }>(),
    supabase
      .from('race_results')
      .select(
        'race_goal_id, official_time_s, swim_time_s, t1_time_s, bike_time_s, t2_time_s, run_time_s, overall_rank, overall_finishers, category, category_rank, category_finishers, bib_number, results_url, weather, nutrition, gear, incidents, comment'
      )
      .eq('user_id', userId)
      .overrideTypes<(RaceResultsRow & { race_goal_id: string })[], { merge: false }>(),
  ])

  const activities = activitiesRes.data ?? []
  const activitiesByRace: Record<string, RaceActivityRow[]> = {}
  for (const activity of activities) {
    const bucket = activitiesByRace[activity.race_goal_id] ?? []
    bucket.push(activity)
    activitiesByRace[activity.race_goal_id] = bucket
  }

  const segmentsByActivity = await fetchRaceSegments(userId, activities)

  const resultsByRace: Record<string, RaceResultsRow> = {}
  for (const result of resultsRes.data ?? []) {
    resultsByRace[result.race_goal_id] = result
  }

  return (
    <RacesWidget
      races={summarizeRaceHistory({
        races: racesRes.data ?? [],
        activitiesByRace,
        segmentsByActivity,
        resultsByRace,
      })}
    />
  )
}

async function fetchRaceSegments(
  userId: string,
  activities: readonly RaceActivityRow[]
): Promise<Record<number, RaceSegmentRow[]>> {
  const ids = activities.map((activity) => activity.garmin_activity_id)
  if (ids.length === 0) return {}
  const supabase = await createClient()
  const { data } = await supabase
    .from('activity_segments')
    .select(
      'garmin_activity_id, segment_index, sport, start_time, duration_s, distance_m, elevation_gain_m, hr_avg, pace_avg_s_per_km'
    )
    .eq('user_id', userId)
    .in('garmin_activity_id', ids)
    .order('segment_index', { ascending: true })
    .overrideTypes<RaceSegmentRow[], { merge: false }>()

  const byActivity: Record<number, RaceSegmentRow[]> = {}
  for (const segment of data ?? []) {
    const bucket = byActivity[segment.garmin_activity_id] ?? []
    bucket.push(segment)
    byActivity[segment.garmin_activity_id] = bucket
  }
  return byActivity
}

async function ColsWidgetLoader({ userId }: { readonly userId: string }) {
  const supabase = await createClient()
  const { data: profile } = await supabase
    .from('athlete_profiles')
    .select('lat, lon')
    .eq('user_id', userId)
    .maybeSingle()

  if (profile?.lat == null || profile.lon == null) {
    return (
      <ChartCard
        title="Mes cols & sommets"
        description="Cols et sommets dans un rayon de 50 km autour de chez toi"
      >
        <EmptyState
          icon={ActivityIcon}
          title="Domicile pas encore situé"
          description="Pas encore assez de données GPS pour situer chez toi."
        />
      </ChartCard>
    )
  }

  const [colsRes, crossingsRes] = await Promise.all([
    supabase.from('cols').select('id, name, latitude, longitude, elevation_m, type'),
    supabase.from('col_crossings').select('col_id, crossed_at').eq('user_id', userId),
  ])

  const cols: ColDto[] = colsRes.data ?? []
  const crossings: ColCrossingRowDto[] = crossingsRes.data ?? []

  const summaries = computeColsSummary({
    homeLat: Number(profile.lat),
    homeLon: Number(profile.lon),
    cols,
    crossings,
  })

  return <ColsWidget summaries={summaries} />
}

export default async function StatsPage({ searchParams }: Props) {
  const userId = await requireOnboarded()
  const params = await searchParams
  const range = parseRange(params.range)
  const selectedSport = parseSport(params.sport)

  return (
    <div className="space-y-8">
      <header className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-muted-foreground text-sm">Suivi longitudinal</p>
          <h1 className="text-2xl font-semibold">Cockpit de performance</h1>
        </div>
        <nav aria-label="Période d’analyse" className="flex gap-1 rounded-md border p-1">
          {ranges.map((days) => (
            <Link
              key={days}
              href={filterHref(days, selectedSport)}
              aria-current={range === days ? 'page' : undefined}
              className={cn(
                'rounded px-3 py-1.5 text-sm font-medium transition-colors',
                range === days ? 'bg-primary text-primary-foreground' : 'hover:bg-accent'
              )}
            >
              {rangeLabel(days)}
            </Link>
          ))}
        </nav>
      </header>

      <nav aria-label="Filtrer par discipline" className="flex gap-2 overflow-x-auto pb-1">
        {sports.map((sport) => (
          <Link
            key={sport.value}
            href={filterHref(range, sport.value)}
            aria-current={selectedSport === sport.value ? 'page' : undefined}
            className={cn(
              'shrink-0 rounded-md border px-3 py-1.5 text-sm transition-colors',
              selectedSport === sport.value
                ? 'border-foreground bg-foreground text-background'
                : 'hover:bg-accent'
            )}
          >
            {sport.label}
          </Link>
        ))}
      </nav>

      <Suspense fallback={<CockpitSkeleton />}>
        <CockpitBody userId={userId} range={range} selectedSport={selectedSport} />
      </Suspense>

      <Suspense fallback={<ColsWidgetSkeleton />}>
        <RacesWidgetLoader userId={userId} />
      </Suspense>

      <Suspense fallback={<ColsWidgetSkeleton />}>
        <ColsWidgetLoader userId={userId} />
      </Suspense>
    </div>
  )
}
