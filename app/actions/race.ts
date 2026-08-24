'use server'

import { revalidatePath } from 'next/cache'
import { z } from 'zod'
import { createClient } from '@/lib/supabase/server'

/**
 * Actions de la vue course (E23) : tag manuel d'une activité et saisie des
 * résultats officiels.
 *
 * Le tag passe par les RPC `set_activity_race` / `clear_activity_race` : la RLS
 * d'`activities` n'autorise que la lecture côté client, écrire directement
 * échouerait silencieusement.
 */

const optionalText = (max: number) =>
  z
    .string()
    .trim()
    .max(max)
    .nullable()
    .transform((value) => (value === '' ? null : value))

const optionalSeconds = (max: number) => z.number().int().min(0).max(max).nullable()
const optionalRank = z.number().int().min(1).max(1_000_000).nullable()

const tagSchema = z.object({
  activityId: z.uuid(),
  raceGoalId: z.uuid(),
})

const retroactiveRaceSchema = z.object({
  activityId: z.uuid(),
  name: z.string().trim().min(1).max(120),
  raceDate: z.iso.date(),
  discipline: z.enum(['triathlon', 'duathlon', 'aquathlon', 'run', 'bike', 'swim', 'autre']),
  location: optionalText(120),
})

const resultsSchema = z.object({
  raceGoalId: z.uuid(),
  officialTimeS: optionalSeconds(172_800),
  swimTimeS: optionalSeconds(86_400),
  t1TimeS: optionalSeconds(7_200),
  bikeTimeS: optionalSeconds(86_400),
  t2TimeS: optionalSeconds(7_200),
  runTimeS: optionalSeconds(86_400),
  overallRank: optionalRank,
  overallFinishers: optionalRank,
  category: optionalText(40),
  categoryRank: optionalRank,
  categoryFinishers: optionalRank,
  bibNumber: optionalText(20),
  resultsUrl: z
    .union([z.literal(''), z.url().max(500).startsWith('http')])
    .nullable()
    .transform((value) => (value === '' ? null : value)),
  weather: optionalText(500),
  nutrition: optionalText(1000),
  gear: optionalText(500),
  incidents: optionalText(1000),
  comment: optionalText(2000),
})

export type RaceTagInput = z.input<typeof tagSchema>
export type RetroactiveRaceInput = z.input<typeof retroactiveRaceSchema>
export type RaceResultsInput = z.input<typeof resultsSchema>

export type RaceActionResult =
  | { success: true; raceGoalId?: string }
  | { success: false; error: string }

async function currentUserId(): Promise<string | null> {
  const supabase = await createClient()
  const { data } = await supabase.auth.getSession()
  return data.session?.user.id ?? null
}

function revalidateRace(raceGoalId: string, activityId?: string): void {
  revalidatePath(`/history/race/${raceGoalId}`)
  if (activityId) revalidatePath(`/history/${activityId}`)
  revalidatePath('/history')
  revalidatePath('/stats')
}

/** Rattache une activité à une course existante (décision de l'athlète). */
export async function tagActivityAsRace(input: RaceTagInput): Promise<RaceActionResult> {
  const parsed = tagSchema.safeParse(input)
  if (!parsed.success) return { success: false, error: 'invalid_input' }
  if (!(await currentUserId())) return { success: false, error: 'unauthenticated' }

  const supabase = await createClient()
  const { error } = await supabase.rpc('set_activity_race', {
    p_activity_id: parsed.data.activityId,
    p_race_goal_id: parsed.data.raceGoalId,
  })
  if (error) return { success: false, error: error.message }

  revalidateRace(parsed.data.raceGoalId, parsed.data.activityId)
  return { success: true, raceGoalId: parsed.data.raceGoalId }
}

/** Détache une activité de sa course, définitivement : le tag manuel gagne sur la détection. */
export async function untagActivityRace(activityId: string): Promise<RaceActionResult> {
  const parsed = z.uuid().safeParse(activityId)
  if (!parsed.success) return { success: false, error: 'invalid_input' }
  if (!(await currentUserId())) return { success: false, error: 'unauthenticated' }

  const supabase = await createClient()
  const { error } = await supabase.rpc('clear_activity_race', { p_activity_id: parsed.data })
  if (error) return { success: false, error: error.message }

  revalidatePath(`/history/${parsed.data}`)
  revalidatePath('/history')
  revalidatePath('/stats')
  return { success: true }
}

/**
 * Crée une course rétroactive et y rattache l'activité — cas de l'épreuve courue
 * avant l'app, ou du dossard pris au dernier moment sans objectif saisi.
 */
export async function createRetroactiveRace(
  input: RetroactiveRaceInput
): Promise<RaceActionResult> {
  const parsed = retroactiveRaceSchema.safeParse(input)
  if (!parsed.success) return { success: false, error: 'invalid_input' }

  const userId = await currentUserId()
  if (!userId) return { success: false, error: 'unauthenticated' }

  const supabase = await createClient()
  const { data, error } = await supabase
    .from('race_goals')
    .insert({
      user_id: userId,
      race_date: parsed.data.raceDate,
      name: parsed.data.name,
      location: parsed.data.location,
      discipline: parsed.data.discipline,
      // Une course passée n'est jamais l'objectif courant : `is_primary` reste faux,
      // sinon elle prendrait la place de la prochaine échéance dans tout le coach.
      is_primary: false,
    })
    .select('id')
    .single()
    .overrideTypes<{ id: string }, { merge: false }>()

  if (error) return { success: false, error: error.message }
  const raceGoalId = data.id

  return tagActivityAsRace({ activityId: parsed.data.activityId, raceGoalId })
}

/** Enregistre les résultats officiels et le ressenti (E23.5 V1 : saisie manuelle). */
export async function saveRaceResults(input: RaceResultsInput): Promise<RaceActionResult> {
  const parsed = resultsSchema.safeParse(input)
  if (!parsed.success) return { success: false, error: 'invalid_input' }

  const userId = await currentUserId()
  if (!userId) return { success: false, error: 'unauthenticated' }

  const supabase = await createClient()
  const { data: race } = await supabase
    .from('race_goals')
    .select('id')
    .eq('id', parsed.data.raceGoalId)
    .eq('user_id', userId)
    .maybeSingle()
  if (!race) return { success: false, error: 'race_not_found' }

  const { error } = await supabase.from('race_results').upsert(
    {
      race_goal_id: parsed.data.raceGoalId,
      user_id: userId,
      official_time_s: parsed.data.officialTimeS,
      swim_time_s: parsed.data.swimTimeS,
      t1_time_s: parsed.data.t1TimeS,
      bike_time_s: parsed.data.bikeTimeS,
      t2_time_s: parsed.data.t2TimeS,
      run_time_s: parsed.data.runTimeS,
      overall_rank: parsed.data.overallRank,
      overall_finishers: parsed.data.overallFinishers,
      category: parsed.data.category,
      category_rank: parsed.data.categoryRank,
      category_finishers: parsed.data.categoryFinishers,
      bib_number: parsed.data.bibNumber,
      results_url: parsed.data.resultsUrl,
      weather: parsed.data.weather,
      nutrition: parsed.data.nutrition,
      gear: parsed.data.gear,
      incidents: parsed.data.incidents,
      comment: parsed.data.comment,
    },
    { onConflict: 'race_goal_id' }
  )

  if (error) return { success: false, error: error.message }

  revalidateRace(parsed.data.raceGoalId)
  return { success: true, raceGoalId: parsed.data.raceGoalId }
}
