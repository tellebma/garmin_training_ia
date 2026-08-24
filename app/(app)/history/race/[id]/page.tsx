import { Suspense } from 'react'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import { ArrowLeft, Award, Flag, Medal, Mountain, Route, Timer, Trophy } from 'lucide-react'
import { MetricTile } from '../../../_components/metric-tile'
import { RaceDebriefCard } from '../../../_components/race-debrief-card'
import { RaceTimelineTable } from '../../../_components/race-timeline-table'
import { ActivityDetailSkeleton } from '../../../_components/skeletons/activity-detail-skeleton'
import { RaceResultsForm } from './race-results-form'
import {
  buildRaceDebrief,
  buildRaceTimeline,
  compareRaces,
  formatClockDelta,
  formatRaceClock,
  resolveRaceElapsed,
  summarizePreparation,
  type RaceActivityRow,
  type RaceGoalRow,
  type RaceResultsRow,
  type RaceSegmentRow,
} from '@/lib/coach/race-analysis'
import { formatDistanceKm, formatDuration } from '@/lib/dashboard/format'
import { requireOnboarded } from '@/lib/onboarding/guard'
import { createClient } from '@/lib/supabase/server'

export const revalidate = 300

const RACE_COLUMNS =
  'id, race_date, name, location, discipline, legs, total_distance_km, total_elevation_gain_m, target_time_seconds, prep_start_date'
const ACTIVITY_COLUMNS =
  'id, garmin_activity_id, start_time, sport, duration_s, distance_m, elevation_gain_m, hr_avg, pace_avg_s_per_km, tss'
const SEGMENT_COLUMNS =
  'garmin_activity_id, segment_index, sport, start_time, duration_s, distance_m, elevation_gain_m, hr_avg, pace_avg_s_per_km'
const RESULTS_COLUMNS =
  'official_time_s, swim_time_s, t1_time_s, bike_time_s, t2_time_s, run_time_s, overall_rank, overall_finishers, category, category_rank, category_finishers, bib_number, results_url, weather, nutrition, gear, incidents, comment'

const DISCIPLINE_LABEL: Readonly<Record<string, string>> = {
  triathlon: 'Triathlon',
  duathlon: 'Duathlon',
  aquathlon: 'Aquathlon',
  run: 'Course à pied',
  bike: 'Vélo',
  swim: 'Natation',
  autre: 'Course',
}

/** « 42 / 310 », ou « 42 » quand le nombre de classés n'est pas connu. */
function formatRank(results: RaceResultsRow | null): string {
  if (!results?.overall_rank) return '—'
  const rank = String(results.overall_rank)
  if (!results.overall_finishers) return rank
  return `${rank} / ${String(results.overall_finishers)}`
}

interface RacePageProps {
  readonly params: Promise<{ readonly id: string }>
}

export default async function RacePage({ params }: RacePageProps) {
  const userId = await requireOnboarded()
  const { id } = await params
  const supabase = await createClient()

  const { data } = await supabase
    .from('race_goals')
    .select(RACE_COLUMNS)
    .eq('user_id', userId)
    .eq('id', id)
    .maybeSingle()

  if (!data) notFound()
  const race = data as RaceGoalRow

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
            {new Date(`${race.race_date}T00:00:00Z`).toLocaleDateString('fr-FR', {
              weekday: 'long',
              day: 'numeric',
              month: 'long',
              year: 'numeric',
              timeZone: 'UTC',
            })}
            {race.location ? ` · ${race.location}` : ''}
          </p>
          <h1 className="flex items-center gap-2 text-2xl font-semibold">
            <Flag size={20} className="text-muted-foreground" />
            {race.name ?? DISCIPLINE_LABEL[race.discipline] ?? 'Course'}
          </h1>
          <p className="text-muted-foreground mt-1 text-sm">
            {DISCIPLINE_LABEL[race.discipline] ?? race.discipline}
            {race.total_distance_km ? ` · ${formatDistanceKm(race.total_distance_km)}` : ''}
            {race.total_elevation_gain_m ? ` · ${String(race.total_elevation_gain_m)} m D+` : ''}
          </p>
        </div>
      </header>

      <Suspense fallback={<ActivityDetailSkeleton />}>
        <RaceBody userId={userId} race={race} />
      </Suspense>
    </div>
  )
}

async function RaceBody({ userId, race }: { readonly userId: string; readonly race: RaceGoalRow }) {
  const supabase = await createClient()

  const [activitiesRes, resultsRes, previousRaceRes, firstTaggedRes] = await Promise.all([
    supabase
      .from('activities')
      .select(ACTIVITY_COLUMNS)
      .eq('user_id', userId)
      .eq('race_goal_id', race.id)
      .order('start_time', { ascending: true }),
    supabase
      .from('race_results')
      .select(RESULTS_COLUMNS)
      .eq('race_goal_id', race.id)
      .maybeSingle()
      .overrideTypes<RaceResultsRow, { merge: false }>(),
    supabase
      .from('race_goals')
      .select('id, race_date, name')
      .eq('user_id', userId)
      .eq('discipline', race.discipline)
      .lt('race_date', race.race_date)
      .order('race_date', { ascending: false })
      .limit(1)
      .maybeSingle()
      .overrideTypes<{ id: string; race_date: string; name: string | null }, { merge: false }>(),
    supabase
      .from('activities')
      .select('race_goal_id, start_time')
      .eq('user_id', userId)
      .not('race_goal_id', 'is', null)
      .order('start_time', { ascending: true })
      .limit(1)
      .maybeSingle()
      .overrideTypes<{ race_goal_id: string | null }, { merge: false }>(),
  ])

  const activities: RaceActivityRow[] = activitiesRes.data ?? []
  const results: RaceResultsRow | null = resultsRes.data
  const previousRace = previousRaceRes.data
  const isFirstRace = firstTaggedRes.data?.race_goal_id === race.id

  const segments = await fetchSegments(supabase, userId, activities)
  const timeline = buildRaceTimeline({ activities, segments })
  const elapsed = resolveRaceElapsed({ timeline, race, results })

  const [previousTimeline, prepActivities] = await Promise.all([
    previousRace ? fetchRaceTimeline(supabase, userId, previousRace.id) : Promise.resolve(null),
    fetchPreparationActivities(supabase, userId, race),
  ])

  const preparation = summarizePreparation(prepActivities, race.prep_start_date, race.race_date)
  const debrief = buildRaceDebrief({ race, timeline, elapsed, previousTimeline, preparation })
  const comparison = previousTimeline ? compareRaces(timeline, previousTimeline) : []

  return (
    <>
      {isFirstRace && (
        <section className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4">
          <p className="flex items-center gap-2 text-sm font-semibold">
            <Award size={16} /> Première course
          </p>
          <p className="text-muted-foreground mt-1 text-sm">
            C’est l’épreuve la plus ancienne de ton historique : le point de départ auquel toutes
            les suivantes se compareront.
          </p>
        </section>
      )}

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MetricTile
          icon={Timer}
          label={elapsed.source === 'official' ? 'Temps officiel' : 'Temps (montre)'}
          value={formatRaceClock(elapsed.totalS)}
          delta={
            elapsed.deltaS === null
              ? null
              : { value: formatClockDelta(elapsed.deltaS), positive: elapsed.deltaS <= 0 }
          }
        />
        <MetricTile
          icon={Trophy}
          label="Objectif"
          value={race.target_time_seconds ? formatRaceClock(race.target_time_seconds) : '—'}
        />
        <MetricTile icon={Medal} label="Classement" value={formatRank(results)} />
        <MetricTile
          icon={Route}
          label="Distance"
          value={formatDistanceKm(race.total_distance_km)}
        />
      </section>

      <RaceDebriefCard debrief={debrief} />

      <section className="rounded-lg border p-4">
        <h2 className="text-base font-semibold">Déroulé de l’épreuve</h2>
        <p className="text-muted-foreground mt-1 mb-4 text-sm">
          Chaque discipline et chaque transition, dans l’ordre de la course.
        </p>
        <RaceTimelineTable timeline={timeline} />
      </section>

      {comparison.length > 0 && previousRace && (
        <section className="rounded-lg border p-4">
          <h2 className="text-base font-semibold">
            Comparaison avec {previousRace.name ?? 'la course précédente'}
          </h2>
          <p className="text-muted-foreground mt-1 mb-4 text-sm">
            Même discipline, le{' '}
            {new Date(`${previousRace.race_date}T00:00:00Z`).toLocaleDateString('fr-FR', {
              timeZone: 'UTC',
            })}
            .
          </p>
          <ul className="space-y-2 text-sm">
            {comparison.map((line) => (
              <li key={line.sport} className="flex items-center justify-between gap-3">
                <span>{line.label}</span>
                <span className="tabular-nums">
                  {formatRaceClock(line.currentS)}{' '}
                  <span className={line.deltaS <= 0 ? 'text-emerald-500' : 'text-red-500'}>
                    ({formatClockDelta(line.deltaS)})
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {preparation.sessions > 0 && (
        <section className="rounded-lg border p-4">
          <h2 className="text-base font-semibold">Le chemin parcouru</h2>
          <p className="text-muted-foreground mt-1 mb-4 text-sm">
            La préparation réellement effectuée avant cette course.
          </p>
          <div className="grid gap-3 sm:grid-cols-3">
            <MetricTile icon={Timer} label="Volume" value={formatDuration(preparation.durationS)} />
            <MetricTile
              icon={Mountain}
              label="Séances"
              value={`${String(preparation.sessions)} en ${String(preparation.weeks)} sem.`}
            />
            <MetricTile
              icon={Route}
              label="Distance cumulée"
              value={formatDistanceKm(preparation.distanceM / 1000)}
            />
          </div>
        </section>
      )}

      <RaceResultsForm raceGoalId={race.id} initialResults={results} />

      {activities.length > 0 && (
        <section className="rounded-lg border p-4">
          <h2 className="text-base font-semibold">Activités de la course</h2>
          <ul className="mt-3 space-y-2 text-sm">
            {activities.map((activity) => (
              <li key={activity.id}>
                <Link href={`/history/${activity.id}`} className="text-primary hover:underline">
                  {new Date(activity.start_time).toLocaleTimeString('fr-FR', {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}{' '}
                  · {activity.sport} · {formatDuration(activity.duration_s)}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  )
}

type SupabaseServerClient = Awaited<ReturnType<typeof createClient>>

async function fetchSegments(
  supabase: SupabaseServerClient,
  userId: string,
  activities: readonly RaceActivityRow[]
): Promise<RaceSegmentRow[]> {
  const ids = activities.map((activity) => activity.garmin_activity_id)
  if (ids.length === 0) return []
  const { data } = await supabase
    .from('activity_segments')
    .select(SEGMENT_COLUMNS)
    .eq('user_id', userId)
    .in('garmin_activity_id', ids)
    .order('segment_index', { ascending: true })
  return data ?? []
}

/** Ligne de temps d'une autre course, pour la comparaison. */
async function fetchRaceTimeline(
  supabase: SupabaseServerClient,
  userId: string,
  raceGoalId: string
) {
  const { data } = await supabase
    .from('activities')
    .select(ACTIVITY_COLUMNS)
    .eq('user_id', userId)
    .eq('race_goal_id', raceGoalId)
    .order('start_time', { ascending: true })
  const activities: RaceActivityRow[] = data ?? []
  if (activities.length === 0) return null
  const segments = await fetchSegments(supabase, userId, activities)
  return buildRaceTimeline({ activities, segments })
}

async function fetchPreparationActivities(
  supabase: SupabaseServerClient,
  userId: string,
  race: RaceGoalRow
): Promise<RaceActivityRow[]> {
  if (!race.prep_start_date) return []
  const { data } = await supabase
    .from('activities')
    .select(ACTIVITY_COLUMNS)
    .eq('user_id', userId)
    .gte('start_time', `${race.prep_start_date}T00:00:00Z`)
    .lt('start_time', `${race.race_date}T00:00:00Z`)
  return data ?? []
}
