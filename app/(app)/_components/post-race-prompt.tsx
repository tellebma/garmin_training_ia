import { PostRaceSheet } from '@/components/coach/post-race-sheet'
import { countedActivities } from '@/lib/activities/scope'
import { postRacePromptSurface, promptWindow } from '@/lib/coach/post-race-prompt'
import {
  buildRaceSalute,
  buildRaceTimeline,
  resolveRaceElapsed,
  type RaceActivityRow,
  type RaceGoalRow,
  type RaceResultsRow,
} from '@/lib/coach/race-analysis'
import { createClient } from '@/lib/supabase/server'

/**
 * La question posée après une course (E26), montée dans le layout de l'app.
 *
 * Composant serveur isolé, à monter sous `<Suspense>` : il ne rejoint PAS le `Promise.all`
 * du layout. Une modale ne doit jamais retarder le rendu de l'application.
 *
 * Rien n'est écrit ici, et rien n'est armé côté worker : la question se dérive d'une
 * requête (cf. `lib/coach/post-race-prompt.ts`).
 */

const RACE_COLUMNS =
  'id, race_date, name, location, discipline, legs, total_distance_km, total_elevation_gain_m, target_time_seconds, post_race_choice, post_race_prompt_count, post_race_prompt_snoozed_until'
const ACTIVITY_COLUMNS =
  'id, garmin_activity_id, start_time, sport, duration_s, distance_m, elevation_gain_m, hr_avg, pace_avg_s_per_km, tss'

interface PromptRaceRow extends RaceGoalRow {
  readonly post_race_choice: string | null
  readonly post_race_prompt_count: number | null
  readonly post_race_prompt_snoozed_until: string | null
}

export async function PostRacePrompt({ userId }: { readonly userId: string }) {
  const supabase = await createClient()
  const today = new Date()
  const { from, to } = promptWindow(today)

  // La course la plus récente de la fenêtre : deux épreuves le même week-end ne doivent
  // pas empiler deux modales — on traite la dernière, l'autre revient ensuite.
  const { data } = await supabase
    .from('race_goals')
    .select(RACE_COLUMNS)
    .eq('user_id', userId)
    .gte('race_date', from)
    .lte('race_date', to)
    .is('post_race_choice', null)
    .order('race_date', { ascending: false })
    .limit(1)
    .maybeSingle()

  const race: PromptRaceRow | null = data
  if (!race) return null

  const surface = postRacePromptSurface(race, today)
  if (!surface) return null

  // Une course sans activité rattachée n'a pas été courue (épreuve annulée, dossard non
  // pris) : il n'y a rien à débriefer et rien à demander. Les activités exclues (E24) ne
  // comptent pas — sinon un doublon supprimé suffirait à « prouver » la course.
  const { data: activityRows } = await countedActivities(
    supabase.from('activities').select(ACTIVITY_COLUMNS).eq('user_id', userId)
  ).eq('race_goal_id', race.id)

  const activities = (activityRows ?? []) as RaceActivityRow[]
  if (activities.length === 0) return null

  const [{ data: segmentRows }, { data: resultsRow }, { count: earlierRaces }] = await Promise.all([
    supabase
      .from('activity_segments')
      .select(
        'garmin_activity_id, segment_index, sport, start_time, duration_s, distance_m, elevation_gain_m, hr_avg, pace_avg_s_per_km'
      )
      .in(
        'garmin_activity_id',
        activities.map((activity) => activity.garmin_activity_id)
      ),
    supabase
      .from('race_results')
      .select('official_time_s')
      .eq('race_goal_id', race.id)
      .maybeSingle(),
    supabase
      .from('race_goals')
      .select('id', { count: 'exact', head: true })
      .eq('user_id', userId)
      .lt('race_date', race.race_date),
  ])

  const timeline = buildRaceTimeline({ activities, segments: segmentRows ?? [] })
  const elapsed = resolveRaceElapsed({
    timeline,
    race,
    results: (resultsRow ?? null) as RaceResultsRow | null,
  })
  if (elapsed.totalS <= 0) return null

  const salute = buildRaceSalute({
    race,
    activities,
    elapsed,
    // La comparaison fine avec la course précédente vit dans le débrief : ici on ne
    // s'en sert que pour choisir un ton, jamais pour produire un second classement.
    previousDeltaS: null,
    isFirstRace: (earlierRaces ?? 0) === 0,
  })

  return (
    <PostRaceSheet
      raceGoalId={race.id}
      raceName={race.name ?? 'Ta course'}
      salute={salute}
      surface={surface}
    />
  )
}
