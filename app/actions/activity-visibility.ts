'use server'

import { revalidatePath } from 'next/cache'
import { z } from 'zod'
import { createClient } from '@/lib/supabase/server'

/**
 * Suppression (réversible) d'une activité — E24.
 *
 * L'activité n'est pas effacée : elle est marquée `excluded_at`. Une suppression
 * physique serait annulée au sync suivant, puisque l'activité existe toujours chez
 * Garmin. L'écriture passe par une RPC `security definer` : la RLS d'`activities`
 * n'autorise que la lecture côté client.
 */

const deleteSchema = z.object({
  activityId: z.uuid(),
  reason: z
    .string()
    .trim()
    .max(200)
    .nullable()
    .transform((value) => (value === '' ? null : value)),
})

export type DeleteActivityInput = z.input<typeof deleteSchema>

export type ActivityVisibilityResult = { success: true } | { success: false; error: string }

async function currentUserId(): Promise<string | null> {
  const supabase = await createClient()
  const { data } = await supabase.auth.getSession()
  return data.session?.user.id ?? null
}

function revalidateActivityViews(activityId: string): void {
  revalidatePath(`/history/${activityId}`)
  revalidatePath('/history')
  revalidatePath('/stats')
  revalidatePath('/today')
}

async function setExcluded(
  activityId: string,
  excluded: boolean,
  reason: string | null
): Promise<ActivityVisibilityResult> {
  if (!(await currentUserId())) return { success: false, error: 'unauthenticated' }

  const supabase = await createClient()
  const { error } = await supabase.rpc('set_activity_excluded', {
    p_activity_id: activityId,
    p_excluded: excluded,
    p_reason: reason,
  })
  if (error) return { success: false, error: error.message }

  revalidateActivityViews(activityId)
  return { success: true }
}

/** Retire l'activité de l'historique et des statistiques. */
export async function deleteActivity(
  input: DeleteActivityInput
): Promise<ActivityVisibilityResult> {
  const parsed = deleteSchema.safeParse(input)
  if (!parsed.success) return { success: false, error: 'invalid_input' }
  return setExcluded(parsed.data.activityId, true, parsed.data.reason)
}

/** Remet une activité supprimée dans l'historique et les statistiques. */
export async function restoreActivity(activityId: string): Promise<ActivityVisibilityResult> {
  const parsed = z.uuid().safeParse(activityId)
  if (!parsed.success) return { success: false, error: 'invalid_input' }
  return setExcluded(parsed.data, false, null)
}
