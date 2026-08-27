'use server'

import { revalidatePath } from 'next/cache'
import { z } from 'zod'
import { TRAINING_MODES } from '@/lib/coach/training-mode'
import { createClient } from '@/lib/supabase/server'

/**
 * Changement de cap d'entraînement (E27).
 *
 * Passe par la RPC `set_training_mode` plutôt que par un update direct : c'est elle qui
 * garde l'ancre de cycle (`training_mode_since`) cohérente — la réécrire à chaque appel
 * repousserait indéfiniment la semaine de décharge.
 */
const modeSchema = z.object({ mode: z.enum(TRAINING_MODES) })

export interface TrainingModeResult {
  readonly success: boolean
  readonly error?: string
}

export async function setTrainingMode(mode: string): Promise<TrainingModeResult> {
  const parsed = modeSchema.safeParse({ mode })
  if (!parsed.success) return { success: false, error: 'invalid_mode' }

  const supabase = await createClient()
  const { error } = await supabase.rpc('set_training_mode', { p_mode: parsed.data.mode })
  if (error) return { success: false, error: 'save_failed' }

  revalidatePath('/profile')
  revalidatePath('/today')
  revalidatePath('/plan')
  return { success: true }
}
