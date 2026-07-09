// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react'
import type { FeatureFlagRow } from '@/lib/admin/types'

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

// Mock the whole Server Action module so the component under test never loads the
// real `../actions`, which transitively pulls in `lib/supabase/server.ts` (reads
// validated env vars at import time) and `next/cache`.
const setFeatureFlag = vi.fn()
vi.mock('@/app/(app)/admin/actions', () => ({
  setFeatureFlag: (...args: unknown[]) => setFeatureFlag(...args) as unknown,
}))

const routerRefresh = vi.fn()
vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: routerRefresh }),
}))

const toastError = vi.fn()
const toastSuccess = vi.fn()
vi.mock('sonner', () => ({
  toast: {
    error: (...args: unknown[]) => toastError(...args) as unknown,
    success: (...args: unknown[]) => toastSuccess(...args) as unknown,
  },
}))

const { computeExpiry, FeatureFlagsList } =
  await import('@/app/(app)/admin/_components/feature-flags-list')

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

const flag: FeatureFlagRow = {
  key: 'maintenance_mode',
  enabled: false,
  expires_at: null,
  description: 'Bascule la page de maintenance pour les non-admins',
  updated_at: '2026-01-01T00:00:00.000Z',
}

describe('FeatureFlagsList — toggle failure branch', () => {
  it('shows a toast.error and keeps the button label unchanged when the action fails', async () => {
    setFeatureFlag.mockResolvedValueOnce({ success: false, error: 'save_failed' })

    render(<FeatureFlagsList flags={[flag]} />)

    const button = screen.getByRole('button', { name: 'Activer' })
    fireEvent.click(button)

    await waitFor(() => {
      expect(toastError).toHaveBeenCalledTimes(1)
    })
    expect(toastError).toHaveBeenCalledWith('Échec de la mise à jour du flag.')

    // Failure path: state must NOT flip to "would have succeeded" — label stays
    // "Activer" (not "Désactiver"), and no client-side refresh happens.
    expect(screen.getByRole('button', { name: 'Activer' })).toBeTruthy()
    expect(routerRefresh).not.toHaveBeenCalled()
  })

  it('triggers a router refresh and no toast on success (control case)', async () => {
    setFeatureFlag.mockResolvedValueOnce({ success: true })

    render(<FeatureFlagsList flags={[flag]} />)

    fireEvent.click(screen.getByRole('button', { name: 'Activer' }))

    await waitFor(() => {
      expect(routerRefresh).toHaveBeenCalledTimes(1)
    })
    expect(toastError).not.toHaveBeenCalled()
  })
})
