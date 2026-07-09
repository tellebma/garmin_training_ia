import { describe, expect, it, vi } from 'vitest'

// feature-flags-list.tsx imports the Server Action module, which in turn imports
// lib/supabase/server.ts — that reads validated env vars at import time. Mock it
// out so this pure-function test doesn't need a real Supabase environment.
vi.mock('@/lib/supabase/server', () => ({ createClient: async () => ({ rpc: vi.fn() }) }))
vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))
vi.mock('next/navigation', () => ({ useRouter: () => ({ refresh: vi.fn() }) }))

const { computeExpiry } = await import('@/app/(app)/admin/_components/feature-flags-list')

describe('computeExpiry', () => {
  it('returns an ISO string at now + durationHours for public_registration_enabled when enabling', () => {
    const now = Date.UTC(2026, 0, 1, 0, 0, 0)
    const result = computeExpiry('public_registration_enabled', true, 24, now)
    expect(result).toBe(new Date(now + 24 * 3_600_000).toISOString())
  })

  it('returns null for any other flag key, even when enabling', () => {
    const now = Date.now()
    expect(computeExpiry('maintenance_mode', true, 24, now)).toBeNull()
    expect(computeExpiry('llm_generation_enabled', true, 1, now)).toBeNull()
  })

  it('returns null when nextEnabled is false, regardless of key', () => {
    const now = Date.now()
    expect(computeExpiry('public_registration_enabled', false, 24, now)).toBeNull()
    expect(computeExpiry('maintenance_mode', false, 24, now)).toBeNull()
  })
})
