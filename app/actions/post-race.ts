'use server'

import { revalidatePath } from 'next/cache'
import { z } from 'zod'
import { createClient } from '@/lib/supabase/server'

/**
 * Réponse et report de la question posée après une course (E26).
 *
 * Les deux passent par des RPC `security definer` : c'est la base qui écrit le choix ET
 * le cap dans le même appel (sans quoi un échec entre les deux laisserait un choix sans
 * effet sur le plan), et c'est elle qui décide de la cadence des relances — le client ne
 * doit pas pouvoir choisir quand on le rappelle.
 */
const answerSchema = z.object({
  raceGoalId: z.uuid(),
  choice: z.enum(['new_race', 'maintain', 'improve', 'dismissed']),
})

const snoozeSchema = z.object({ raceGoalId: z.uuid() })

export interface PostRaceResult {
  readonly success: boolean
  readonly error?: string
}

function revalidateSurfaces(): void {
  revalidatePath('/today')
  revalidatePath('/plan')
  revalidatePath('/profile')
}

export async function answerPostRacePrompt(
  raceGoalId: string,
  choice: string
): Promise<PostRaceResult> {
  const parsed = answerSchema.safeParse({ raceGoalId, choice })
  if (!parsed.success) return { success: false, error: 'invalid_input' }

  const supabase = await createClient()
  const { error } = await supabase.rpc('answer_post_race_prompt', {
    p_race_goal_id: parsed.data.raceGoalId,
    p_choice: parsed.data.choice,
  })
  if (error) return { success: false, error: 'save_failed' }

  revalidateSurfaces()
  return { success: true }
}

export async function snoozePostRacePrompt(raceGoalId: string): Promise<PostRaceResult> {
  const parsed = snoozeSchema.safeParse({ raceGoalId })
  if (!parsed.success) return { success: false, error: 'invalid_input' }

  const supabase = await createClient()
  const { error } = await supabase.rpc('snooze_post_race_prompt', {
    p_race_goal_id: parsed.data.raceGoalId,
  })
  if (error) return { success: false, error: 'save_failed' }

  revalidateSurfaces()
  return { success: true }
}
