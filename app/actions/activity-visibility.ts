'use server'

import { revalidatePath } from 'next/cache'
import { z } from 'zod'
import { createClient } from '@/lib/supabase/server'
import { workerRecomputeState } from '@/lib/worker'

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

export type ActivityVisibilityResult =
  | { success: true; loadRecomputed: boolean }
  | { success: false; error: string }

async function currentSession(): Promise<{ userId: string; jwt: string } | null> {
  const supabase = await createClient()
  const { data } = await supabase.auth.getSession()
  const session = data.session
  return session ? { userId: session.user.id, jwt: session.access_token } : null
}

/**
 * Recalcule la charge après coup — best effort.
 *
 * Supprimer une activité en double corrige le TSS du jour, donc CTL/ATL/TSB : les
 * laisser faux jusqu'au cron de 05:00 UTC, c'est afficher une forme erronée à
 * l'athlète qui vient précisément de corriger la donnée. Si le worker ne répond
 * pas, la suppression reste acquise et le cron rattrapera — l'action ne doit pas
 * échouer pour autant.
 */
async function recomputeLoad(jwt: string): Promise<boolean> {
  try {
    const result = await workerRecomputeState(jwt)
    return result.status === 'ok'
  } catch {
    return false
  }
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
  const session = await currentSession()
  if (!session) return { success: false, error: 'unauthenticated' }

  const supabase = await createClient()
  const { error } = await supabase.rpc('set_activity_excluded', {
    p_activity_id: activityId,
    p_excluded: excluded,
    p_reason: reason,
  })
  if (error) return { success: false, error: error.message }

  const loadRecomputed = await recomputeLoad(session.jwt)
  revalidateActivityViews(activityId)
  return { success: true, loadRecomputed }
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
