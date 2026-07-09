'use server'

import { revalidatePath } from 'next/cache'
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
