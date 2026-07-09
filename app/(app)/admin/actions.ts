'use server'

import { revalidatePath } from 'next/cache'
import { z } from 'zod'
import { createClient } from '@/lib/supabase/server'

export type AdminActionError = 'expiry_required' | 'save_failed'
export type ActionResult = { success: true } | { success: false; error: AdminActionError }

interface SetFeatureFlagInput {
  key: string
  enabled: boolean
  expiresAt: string | null
}

export async function setFeatureFlag(input: SetFeatureFlagInput): Promise<ActionResult> {
  if (input.key === 'public_registration_enabled' && input.enabled && !input.expiresAt) {
    return { success: false, error: 'expiry_required' }
  }
  const supabase = await createClient()
  const result = await supabase.rpc('admin_set_feature_flag', {
    p_key: input.key,
    p_enabled: input.enabled,
    p_expires_at: input.expiresAt,
  })
  if (result.error) return { success: false, error: 'save_failed' }
  revalidatePath('/admin')
  return { success: true }
}

const addAllowedEmailSchema = z.object({
  email: z.email().transform((s) => s.toLowerCase().trim()),
  note: z.string().nullable(),
})

export async function addAllowedEmail(input: {
  email: string
  note: string | null
}): Promise<ActionResult> {
  const parsed = addAllowedEmailSchema.safeParse(input)
  if (!parsed.success) return { success: false, error: 'save_failed' }
  const supabase = await createClient()
  const result = await supabase.rpc('admin_add_allowed_email', {
    p_email: parsed.data.email,
    p_note: parsed.data.note,
  })
  if (result.error) return { success: false, error: 'save_failed' }
  revalidatePath('/admin')
  return { success: true }
}

export async function removeAllowedEmail(email: string): Promise<ActionResult> {
  const supabase = await createClient()
  const result = await supabase.rpc('admin_remove_allowed_email', { p_email: email })
  if (result.error) return { success: false, error: 'save_failed' }
  revalidatePath('/admin')
  return { success: true }
}
