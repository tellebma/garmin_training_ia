'use server'

import { revalidatePath } from 'next/cache'
import { z } from 'zod'
import { createClient } from '@/lib/supabase/server'

const optionalText = (max: number) =>
  z
    .string()
    .trim()
    .max(max)
    .nullable()
    .transform((value) => (value === '' ? null : value))

const feedbackSchema = z.object({
  activityId: z.uuid(),
  rpe: z.number().int().min(1).max(10),
  fatigue: z.number().int().min(1).max(5).nullable(),
  soreness: z.number().int().min(1).max(5).nullable(),
  pain: z.number().int().min(0).max(5).nullable(),
  mood: z.number().int().min(1).max(5).nullable(),
  perceivedDifficulty: z.enum(['easier', 'as_expected', 'harder']).nullable(),
  painArea: optionalText(120),
  comment: optionalText(500),
})

export type ActivityFeedbackInput = z.input<typeof feedbackSchema>

export type ActivityFeedbackResult = { success: true } | { success: false; error: string }

export async function saveActivityFeedback(
  input: ActivityFeedbackInput
): Promise<ActivityFeedbackResult> {
  const parsed = feedbackSchema.safeParse(input)
  if (!parsed.success) return { success: false, error: 'invalid_feedback' }

  const supabase = await createClient()
  const { data: sessionData } = await supabase.auth.getSession()
  const userId = sessionData.session?.user.id
  if (!userId) return { success: false, error: 'unauthenticated' }

  const { data: activity, error: activityError } = await supabase
    .from('activities')
    .select('id')
    .eq('id', parsed.data.activityId)
    .eq('user_id', userId)
    .maybeSingle()

  if (activityError) return { success: false, error: activityError.message }
  if (!activity) return { success: false, error: 'activity_not_found' }

  const { error } = await supabase.from('activity_feedback').upsert(
    {
      user_id: userId,
      activity_id: parsed.data.activityId,
      rpe: parsed.data.rpe,
      fatigue: parsed.data.fatigue,
      soreness: parsed.data.soreness,
      pain: parsed.data.pain,
      mood: parsed.data.mood,
      perceived_difficulty: parsed.data.perceivedDifficulty,
      pain_area: parsed.data.painArea,
      comment: parsed.data.comment,
      schema_version: 1,
    },
    { onConflict: 'user_id,activity_id' }
  )

  if (error) return { success: false, error: error.message }

  revalidatePath(`/history/${parsed.data.activityId}`)
  revalidatePath('/stats')
  revalidatePath('/today')
  return { success: true }
}
