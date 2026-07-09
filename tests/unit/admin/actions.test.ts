import { describe, expect, it, vi, beforeEach } from 'vitest'

const revalidatePath = vi.fn()
vi.mock('next/cache', () => ({
  revalidatePath: (path: string): void => {
    revalidatePath(path)
  },
}))

const mockSupabase = { rpc: vi.fn() }
vi.mock('@/lib/supabase/server', () => ({ createClient: async () => mockSupabase }))

import { setFeatureFlag, addAllowedEmail, removeAllowedEmail } from '@/app/(app)/admin/actions'

beforeEach(() => {
  mockSupabase.rpc.mockReset()
  revalidatePath.mockReset()
})

describe('setFeatureFlag', () => {
  it('calls admin_set_feature_flag with the right args and revalidates /admin', async () => {
    mockSupabase.rpc.mockResolvedValueOnce({ data: { key: 'maintenance_mode' }, error: null })
    const result = await setFeatureFlag({ key: 'maintenance_mode', enabled: true, expiresAt: null })
    expect(mockSupabase.rpc).toHaveBeenCalledWith('admin_set_feature_flag', {
      p_key: 'maintenance_mode',
      p_enabled: true,
      p_expires_at: null,
    })
    expect(result).toEqual({ success: true })
    expect(revalidatePath).toHaveBeenCalledWith('/admin')
  })

  it('rejects enabling public_registration_enabled without an expiry (client-side guard)', async () => {
    const result = await setFeatureFlag({
      key: 'public_registration_enabled',
      enabled: true,
      expiresAt: null,
    })
    expect(result).toEqual({ success: false, error: 'expiry_required' })
    expect(mockSupabase.rpc).not.toHaveBeenCalled()
  })

  it('returns save_failed when the RPC errors, without revalidating', async () => {
    mockSupabase.rpc.mockResolvedValueOnce({ data: null, error: { message: 'not authorized' } })
    const result = await setFeatureFlag({ key: 'maintenance_mode', enabled: true, expiresAt: null })
    expect(result).toEqual({ success: false, error: 'save_failed' })
    expect(revalidatePath).not.toHaveBeenCalled()
  })
})

describe('addAllowedEmail', () => {
  it('normalizes email to lowercase and calls the RPC', async () => {
    mockSupabase.rpc.mockResolvedValueOnce({ data: { email: 'ami@example.com' }, error: null })
    const result = await addAllowedEmail({ email: 'AMI@Example.com', note: 'copain de club' })
    expect(mockSupabase.rpc).toHaveBeenCalledWith('admin_add_allowed_email', {
      p_email: 'ami@example.com',
      p_note: 'copain de club',
    })
    expect(result).toEqual({ success: true })
  })

  it('rejects an invalid email before calling the RPC', async () => {
    const result = await addAllowedEmail({ email: 'not-an-email', note: null })
    expect(result).toEqual({ success: false, error: 'save_failed' })
    expect(mockSupabase.rpc).not.toHaveBeenCalled()
  })
})

describe('removeAllowedEmail', () => {
  it('calls admin_remove_allowed_email and revalidates /admin', async () => {
    mockSupabase.rpc.mockResolvedValueOnce({ data: null, error: null })
    const result = await removeAllowedEmail('ami@example.com')
    expect(mockSupabase.rpc).toHaveBeenCalledWith('admin_remove_allowed_email', {
      p_email: 'ami@example.com',
    })
    expect(result).toEqual({ success: true })
    expect(revalidatePath).toHaveBeenCalledWith('/admin')
  })
})
