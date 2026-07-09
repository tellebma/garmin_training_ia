// @vitest-environment jsdom
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react'
import type { PerfInput } from '@/lib/onboarding/schemas'

beforeAll(() => {
  process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co'
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'anon-key-test'
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const saveStepPerso = vi.fn()
const saveStepRace = vi.fn()
const saveStepPerf = vi.fn()
const saveStepDispo = vi.fn()
const syncGarminProfile = vi.fn()

const toastSuccess = vi.fn()
const toastError = vi.fn()
const toastInfo = vi.fn()
const toastWarning = vi.fn()

vi.mock('@/app/(app)/onboarding/actions', () => ({
  saveStepPerso: (...a: unknown[]) => saveStepPerso(...a) as unknown,
  saveStepRace: (...a: unknown[]) => saveStepRace(...a) as unknown,
  saveStepPerf: (...a: unknown[]) => saveStepPerf(...a) as unknown,
  saveStepDispo: (...a: unknown[]) => saveStepDispo(...a) as unknown,
  syncGarminProfile: (...a: unknown[]) => syncGarminProfile(...a) as unknown,
}))

vi.mock('sonner', () => ({
  toast: {
    success: (...a: unknown[]) => toastSuccess(...a) as unknown,
    error: (...a: unknown[]) => toastError(...a) as unknown,
    info: (...a: unknown[]) => toastInfo(...a) as unknown,
    warning: (...a: unknown[]) => toastWarning(...a) as unknown,
  },
}))

vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}))

type PerfInitial = PerfInput & { garmin_synced_at: string | null }

const baseInitial: PerfInitial = {
  ftp_watts: 245,
  vma_kmh: 16.5,
  fc_max_bpm: 185,
  css_per_100m_s: 95,
  garmin_synced_at: '2026-05-15T10:00:00Z',
}

const emptyInitial: PerfInitial = {
  ftp_watts: undefined,
  vma_kmh: undefined,
  fc_max_bpm: undefined,
  css_per_100m_s: undefined,
  garmin_synced_at: null,
}

describe('PerfEditForm', () => {
  it('renders read-only summary with initial values', async () => {
    const { PerfEditForm } = await import('@/app/(app)/profile/_components/perf-edit-form')
    render(<PerfEditForm initial={baseInitial} />)
    expect(screen.getByRole('heading', { name: /Performance/ })).toBeTruthy()
    expect(screen.getByText(/245 W/)).toBeTruthy()
    expect(screen.getByText(/16\.5 km\/h/)).toBeTruthy()
    expect(screen.getByText(/185 bpm/)).toBeTruthy()
    expect(screen.getByText(/95 s\/100m/)).toBeTruthy()
    expect(screen.getByText(/Synchronisé de Garmin le/)).toBeTruthy()
    expect(screen.getByRole('button', { name: /Modifier/ })).toBeTruthy()
  })

  it('shows em-dashes and no sync banner when initial values are empty', async () => {
    const { PerfEditForm } = await import('@/app/(app)/profile/_components/perf-edit-form')
    render(<PerfEditForm initial={emptyInitial} />)
    const dashes = screen.getAllByText('—')
    expect(dashes.length).toBe(4)
    expect(screen.queryByText(/Synchronisé de Garmin le/)).toBeNull()
  })

  it('switches to edit mode after clicking Modifier', async () => {
    const { PerfEditForm } = await import('@/app/(app)/profile/_components/perf-edit-form')
    render(<PerfEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    expect(screen.getByLabelText(/FTP/)).toBeTruthy()
    expect(screen.getByLabelText(/VMA/)).toBeTruthy()
    expect(screen.getByLabelText(/FC max/)).toBeTruthy()
    expect(screen.getByLabelText(/CSS/)).toBeTruthy()
    expect(screen.getByRole('button', { name: /Enregistrer/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Annuler/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Sync Garmin/ })).toBeTruthy()
  })

  it('pre-fills input values from initial when entering edit mode', async () => {
    const { PerfEditForm } = await import('@/app/(app)/profile/_components/perf-edit-form')
    render(<PerfEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    expect(screen.getByLabelText<HTMLInputElement>(/FTP/).value).toBe('245')
    expect(screen.getByLabelText<HTMLInputElement>(/VMA/).value).toBe('16.5')
    expect(screen.getByLabelText<HTMLInputElement>(/FC max/).value).toBe('185')
    expect(screen.getByLabelText<HTMLInputElement>(/CSS/).value).toBe('95')
  })

  it('updates numeric inputs in edit mode', async () => {
    const { PerfEditForm } = await import('@/app/(app)/profile/_components/perf-edit-form')
    render(<PerfEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    const ftp = screen.getByLabelText<HTMLInputElement>(/FTP/)
    const vma = screen.getByLabelText<HTMLInputElement>(/VMA/)
    const fcmax = screen.getByLabelText<HTMLInputElement>(/FC max/)
    fireEvent.change(ftp, { target: { value: '260' } })
    fireEvent.change(vma, { target: { value: '17.2' } })
    fireEvent.change(fcmax, { target: { value: '190' } })
    expect(ftp.value).toBe('260')
    expect(vma.value).toBe('17.2')
    expect(fcmax.value).toBe('190')
  })

  it('Annuler reverts edit mode and restores initial values', async () => {
    const { PerfEditForm } = await import('@/app/(app)/profile/_components/perf-edit-form')
    render(<PerfEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.change(screen.getByLabelText(/FTP/), { target: { value: '999' } })
    fireEvent.click(screen.getByRole('button', { name: /Annuler/ }))
    expect(saveStepPerf).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: /Modifier/ })).toBeTruthy()
    // Re-enter edit mode and ensure ftp got reverted to initial value
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    expect(screen.getByLabelText<HTMLInputElement>(/FTP/).value).toBe('245')
  })

  it('submits the form successfully and exits edit mode', async () => {
    saveStepPerf.mockResolvedValueOnce({ success: true })
    const { PerfEditForm } = await import('@/app/(app)/profile/_components/perf-edit-form')
    render(<PerfEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.click(screen.getByRole('button', { name: /Enregistrer/ }))
    await waitFor(() => {
      expect(saveStepPerf).toHaveBeenCalledTimes(1)
    })
    const call = saveStepPerf.mock.calls[0]?.[0] as Record<string, unknown>
    expect(call.ftp_watts).toBe(245)
    expect(call.vma_kmh).toBe(16.5)
    expect(call.fc_max_bpm).toBe(185)
    expect(call.css_per_100m_s).toBe(95)
    await waitFor(() => {
      expect(toastSuccess).toHaveBeenCalled()
    })
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Modifier/ })).toBeTruthy()
    })
  })

  it('submits with undefined fields when inputs are blank', async () => {
    saveStepPerf.mockResolvedValueOnce({ success: true })
    const { PerfEditForm } = await import('@/app/(app)/profile/_components/perf-edit-form')
    render(<PerfEditForm initial={emptyInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.click(screen.getByRole('button', { name: /Enregistrer/ }))
    await waitFor(() => {
      expect(saveStepPerf).toHaveBeenCalledTimes(1)
    })
    const call = saveStepPerf.mock.calls[0]?.[0] as Record<string, unknown>
    expect(call.ftp_watts).toBeUndefined()
    expect(call.vma_kmh).toBeUndefined()
    expect(call.fc_max_bpm).toBeUndefined()
    expect(call.css_per_100m_s).toBeUndefined()
  })

  it('renders field errors when action returns errors map', async () => {
    saveStepPerf.mockResolvedValueOnce({
      success: false,
      errors: {
        ftp_watts: ['Trop bas'],
        vma_kmh: ['Trop élevé'],
        fc_max_bpm: ['Invalide'],
      },
    })
    const { PerfEditForm } = await import('@/app/(app)/profile/_components/perf-edit-form')
    render(<PerfEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.click(screen.getByRole('button', { name: /Enregistrer/ }))
    await waitFor(() => {
      expect(screen.getByText('Trop bas')).toBeTruthy()
    })
    expect(screen.getByText('Trop élevé')).toBeTruthy()
    expect(screen.getByText('Invalide')).toBeTruthy()
    // Stays in edit mode
    expect(screen.getByRole('button', { name: /Enregistrer/ })).toBeTruthy()
  })

  it('shows toast.error on generic save failure (no errors map)', async () => {
    saveStepPerf.mockResolvedValueOnce({ success: false })
    const { PerfEditForm } = await import('@/app/(app)/profile/_components/perf-edit-form')
    render(<PerfEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.click(screen.getByRole('button', { name: /Enregistrer/ }))
    await waitFor(() => {
      expect(toastError).toHaveBeenCalled()
    })
    expect(screen.getByRole('button', { name: /Enregistrer/ })).toBeTruthy()
  })

  it('Sync Garmin success updates fields and sets synced banner', async () => {
    syncGarminProfile.mockResolvedValueOnce({
      status: 'ok',
      fetched: { ftp_watts: 260, vma_kmh: 17, fc_max_bpm: 190 },
    })
    const { PerfEditForm } = await import('@/app/(app)/profile/_components/perf-edit-form')
    render(<PerfEditForm initial={emptyInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.click(screen.getByRole('button', { name: /Sync Garmin/ }))
    await waitFor(() => {
      expect(syncGarminProfile).toHaveBeenCalledTimes(1)
    })
    await waitFor(() => {
      expect(screen.getByLabelText<HTMLInputElement>(/FTP/).value).toBe('260')
    })
    expect(screen.getByLabelText<HTMLInputElement>(/VMA/).value).toBe('17')
    expect(screen.getByLabelText<HTMLInputElement>(/FC max/).value).toBe('190')
    expect(toastSuccess).toHaveBeenCalled()
    expect(screen.getByText(/Synchronisé de Garmin le/)).toBeTruthy()
  })

  it('Sync Garmin ok with empty fetched object shows warning + keeps inputs', async () => {
    syncGarminProfile.mockResolvedValueOnce({ status: 'ok', fetched: {} })
    const { PerfEditForm } = await import('@/app/(app)/profile/_components/perf-edit-form')
    render(<PerfEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.click(screen.getByRole('button', { name: /Sync Garmin/ }))
    await waitFor(() => {
      expect(syncGarminProfile).toHaveBeenCalled()
    })
    // Garmin returned no value -> dedicated warning rather than misleading success
    await waitFor(() => {
      expect(toastWarning).toHaveBeenCalled()
    })
    expect(toastSuccess).not.toHaveBeenCalled()
    // Inputs remain unchanged from initial
    expect(screen.getByLabelText<HTMLInputElement>(/FTP/).value).toBe('245')
    expect(screen.getByLabelText<HTMLInputElement>(/VMA/).value).toBe('16.5')
    expect(screen.getByLabelText<HTMLInputElement>(/FC max/).value).toBe('185')
  })

  it('Sync Garmin rate_limited shows toast.warning', async () => {
    syncGarminProfile.mockResolvedValueOnce({ status: 'rate_limited' })
    const { PerfEditForm } = await import('@/app/(app)/profile/_components/perf-edit-form')
    render(<PerfEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.click(screen.getByRole('button', { name: /Sync Garmin/ }))
    await waitFor(() => {
      expect(toastWarning).toHaveBeenCalled()
    })
  })

  it('Sync Garmin auth_failed shows toast.error', async () => {
    syncGarminProfile.mockResolvedValueOnce({ status: 'auth_failed' })
    const { PerfEditForm } = await import('@/app/(app)/profile/_components/perf-edit-form')
    render(<PerfEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.click(screen.getByRole('button', { name: /Sync Garmin/ }))
    await waitFor(() => {
      expect(toastError).toHaveBeenCalled()
    })
  })

  it('Sync Garmin no_credentials shows toast.error', async () => {
    syncGarminProfile.mockResolvedValueOnce({ status: 'no_credentials' })
    const { PerfEditForm } = await import('@/app/(app)/profile/_components/perf-edit-form')
    render(<PerfEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.click(screen.getByRole('button', { name: /Sync Garmin/ }))
    await waitFor(() => {
      expect(toastError).toHaveBeenCalled()
    })
  })

  it('Sync Garmin unknown status falls through to generic error toast', async () => {
    syncGarminProfile.mockResolvedValueOnce({ status: 'oops' })
    const { PerfEditForm } = await import('@/app/(app)/profile/_components/perf-edit-form')
    render(<PerfEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.click(screen.getByRole('button', { name: /Sync Garmin/ }))
    await waitFor(() => {
      expect(toastError).toHaveBeenCalled()
    })
  })

  it('shows loading label while saving', async () => {
    let resolveFn: (value: { success: boolean }) => void = () => {
      // overwritten in the executor below
    }
    const pending = new Promise<{ success: boolean }>((resolve) => {
      resolveFn = resolve
    })
    saveStepPerf.mockReturnValueOnce(pending)
    const { PerfEditForm } = await import('@/app/(app)/profile/_components/perf-edit-form')
    render(<PerfEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.click(screen.getByRole('button', { name: /Enregistrer/ }))
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Sauvegarde\.\.\./ })).toBeTruthy()
    })
    resolveFn({ success: true })
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Modifier/ })).toBeTruthy()
    })
  })

  it('shows syncing label while sync is in flight', async () => {
    let resolveFn: (value: { status: string; fetched?: Record<string, number> }) => void = () => {
      // overwritten in the executor below
    }
    const pending = new Promise<{ status: string; fetched?: Record<string, number> }>((resolve) => {
      resolveFn = resolve
    })
    syncGarminProfile.mockReturnValueOnce(pending)
    const { PerfEditForm } = await import('@/app/(app)/profile/_components/perf-edit-form')
    render(<PerfEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.click(screen.getByRole('button', { name: /Sync Garmin/ }))
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Sync\.\.\./ })).toBeTruthy()
    })
    expect(screen.getByText(/Récupération depuis Garmin/)).toBeTruthy()
    resolveFn({ status: 'ok', fetched: {} })
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Sync Garmin/ })).toBeTruthy()
    })
  })
})
