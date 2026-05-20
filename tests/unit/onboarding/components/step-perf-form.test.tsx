// @vitest-environment jsdom
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react'

beforeAll(() => {
  process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co'
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'anon-key-test'
})

afterEach(cleanup)

const saveStepPerf = vi.fn()
const syncGarminProfile = vi.fn()

vi.mock('@/app/(app)/onboarding/actions', () => ({
  saveStepPerso: vi.fn(),
  saveStepRace: vi.fn(),
  saveStepPerf: (...a: unknown[]) => saveStepPerf(...a) as unknown,
  saveStepDispo: vi.fn(),
  syncGarminProfile: (...a: unknown[]) => syncGarminProfile(...a) as unknown,
  finalizeOnboarding: vi.fn(),
}))
vi.mock('../actions', () => ({
  saveStepPerso: vi.fn(),
  saveStepRace: vi.fn(),
  saveStepPerf: (...a: unknown[]) => saveStepPerf(...a) as unknown,
  saveStepDispo: vi.fn(),
  syncGarminProfile: (...a: unknown[]) => syncGarminProfile(...a) as unknown,
  finalizeOnboarding: vi.fn(),
}))

const toastError = vi.fn()
const toastWarning = vi.fn()
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: toastError, info: vi.fn(), warning: toastWarning },
}))

beforeEach(() => {
  saveStepPerf.mockReset()
  syncGarminProfile.mockReset()
  toastError.mockReset()
  toastWarning.mockReset()
})

describe('StepPerfForm', () => {
  it('renders empty fields when defaults are blank and synced_at is set (no auto-sync)', async () => {
    const { StepPerfForm } = await import('@/app/(app)/onboarding/_components/step-perf-form')
    render(
      <StepPerfForm defaultValues={{ garmin_synced_at: '2026-05-15T10:00:00Z' }} onDone={vi.fn()} />
    )
    expect(screen.getByLabelText(/FTP/)).toBeTruthy()
    expect(screen.getByLabelText(/VMA/)).toBeTruthy()
    expect(screen.getByLabelText(/FC max/)).toBeTruthy()
    expect(screen.getByLabelText<HTMLInputElement>(/FTP/).value).toBe('')
    expect(screen.getByLabelText<HTMLInputElement>(/VMA/).value).toBe('')
    expect(screen.getByLabelText<HTMLInputElement>(/FC max/).value).toBe('')
    // syncGarminProfile must NOT be called since garmin_synced_at is set
    expect(syncGarminProfile).not.toHaveBeenCalled()
  })

  it('renders provided default values', async () => {
    const { StepPerfForm } = await import('@/app/(app)/onboarding/_components/step-perf-form')
    render(
      <StepPerfForm
        defaultValues={{
          ftp_watts: 245,
          vma_kmh: 16.5,
          fc_max_bpm: 185,
          garmin_synced_at: '2026-05-15T10:00:00Z',
        }}
        onDone={vi.fn()}
      />
    )
    expect(screen.getByLabelText<HTMLInputElement>(/FTP/).value).toBe('245')
    expect(screen.getByLabelText<HTMLInputElement>(/VMA/).value).toBe('16.5')
    expect(screen.getByLabelText<HTMLInputElement>(/FC max/).value).toBe('185')
  })

  it('auto-fetches from Garmin on mount when garmin_synced_at is null', async () => {
    syncGarminProfile.mockResolvedValue({
      status: 'ok',
      fetched: { ftp_watts: 250, vma_kmh: 17, fc_max_bpm: 190 },
    })
    const { StepPerfForm } = await import('@/app/(app)/onboarding/_components/step-perf-form')
    render(<StepPerfForm defaultValues={{ garmin_synced_at: null }} onDone={vi.fn()} />)
    await waitFor(() => {
      expect(syncGarminProfile).toHaveBeenCalledTimes(1)
    })
    await waitFor(() => {
      expect(screen.getByLabelText<HTMLInputElement>(/FTP/).value).toBe('250')
    })
    expect(screen.getByLabelText<HTMLInputElement>(/VMA/).value).toBe('17')
    expect(screen.getByLabelText<HTMLInputElement>(/FC max/).value).toBe('190')
  })

  it('handles rate-limited Garmin response with a warning toast', async () => {
    syncGarminProfile.mockResolvedValue({ status: 'rate_limited' })
    const { StepPerfForm } = await import('@/app/(app)/onboarding/_components/step-perf-form')
    render(<StepPerfForm defaultValues={{ garmin_synced_at: null }} onDone={vi.fn()} />)
    await waitFor(() => {
      expect(toastWarning).toHaveBeenCalled()
    })
  })

  it('handles auth_failed Garmin response with an error toast', async () => {
    syncGarminProfile.mockResolvedValue({ status: 'auth_failed' })
    const { StepPerfForm } = await import('@/app/(app)/onboarding/_components/step-perf-form')
    render(<StepPerfForm defaultValues={{ garmin_synced_at: null }} onDone={vi.fn()} />)
    await waitFor(() => {
      expect(toastError).toHaveBeenCalled()
    })
  })

  it('updates FTP input on change', async () => {
    const { StepPerfForm } = await import('@/app/(app)/onboarding/_components/step-perf-form')
    render(
      <StepPerfForm defaultValues={{ garmin_synced_at: '2026-05-15T10:00:00Z' }} onDone={vi.fn()} />
    )
    const input = screen.getByLabelText<HTMLInputElement>(/FTP/)
    fireEvent.change(input, { target: { value: '260' } })
    expect(input.value).toBe('260')
  })

  it('submits perf fields and calls onDone with nextStep', async () => {
    saveStepPerf.mockResolvedValue({ success: true, nextStep: 'dispo' })
    const onDone = vi.fn()
    const { StepPerfForm } = await import('@/app/(app)/onboarding/_components/step-perf-form')
    render(
      <StepPerfForm defaultValues={{ garmin_synced_at: '2026-05-15T10:00:00Z' }} onDone={onDone} />
    )
    fireEvent.change(screen.getByLabelText(/FTP/), { target: { value: '245' } })
    fireEvent.change(screen.getByLabelText(/VMA/), { target: { value: '16.5' } })
    fireEvent.change(screen.getByLabelText(/FC max/), { target: { value: '185' } })
    fireEvent.click(screen.getByRole('button', { name: /Suivant/ }))
    await waitFor(() => {
      expect(saveStepPerf).toHaveBeenCalledTimes(1)
    })
    const call = saveStepPerf.mock.calls[0]?.[0] as Record<string, unknown>
    expect(call.ftp_watts).toBe(245)
    expect(call.vma_kmh).toBe(16.5)
    expect(call.fc_max_bpm).toBe(185)
    await waitFor(() => {
      expect(onDone).toHaveBeenCalledWith('dispo')
    })
  })

  it('submits with undefined values when fields are blank', async () => {
    saveStepPerf.mockResolvedValue({ success: true, nextStep: 'dispo' })
    const { StepPerfForm } = await import('@/app/(app)/onboarding/_components/step-perf-form')
    render(
      <StepPerfForm defaultValues={{ garmin_synced_at: '2026-05-15T10:00:00Z' }} onDone={vi.fn()} />
    )
    fireEvent.click(screen.getByRole('button', { name: /Suivant/ }))
    await waitFor(() => {
      expect(saveStepPerf).toHaveBeenCalledTimes(1)
    })
    const call = saveStepPerf.mock.calls[0]?.[0] as Record<string, unknown>
    expect(call.ftp_watts).toBeUndefined()
    expect(call.vma_kmh).toBeUndefined()
    expect(call.fc_max_bpm).toBeUndefined()
  })

  it('displays errors when server returns validation errors', async () => {
    saveStepPerf.mockResolvedValue({
      success: false,
      errors: { ftp_watts: ['Trop bas'], vma_kmh: ['Trop élevé'], fc_max_bpm: ['Invalide'] },
    })
    const onDone = vi.fn()
    const { StepPerfForm } = await import('@/app/(app)/onboarding/_components/step-perf-form')
    render(
      <StepPerfForm defaultValues={{ garmin_synced_at: '2026-05-15T10:00:00Z' }} onDone={onDone} />
    )
    fireEvent.click(screen.getByRole('button', { name: /Suivant/ }))
    await waitFor(() => {
      expect(screen.getByText(/Trop bas/)).toBeTruthy()
    })
    expect(screen.getByText(/Trop élevé/)).toBeTruthy()
    expect(screen.getByText(/Invalide/)).toBeTruthy()
    expect(onDone).not.toHaveBeenCalled()
  })

  it('shows generic error toast on non-validation failure', async () => {
    saveStepPerf.mockResolvedValue({ success: false })
    const { StepPerfForm } = await import('@/app/(app)/onboarding/_components/step-perf-form')
    render(
      <StepPerfForm defaultValues={{ garmin_synced_at: '2026-05-15T10:00:00Z' }} onDone={vi.fn()} />
    )
    fireEvent.click(screen.getByRole('button', { name: /Suivant/ }))
    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith('Erreur de sauvegarde, réessaye.')
    })
  })

  it('shows the formatted synced timestamp when garmin_synced_at is set', async () => {
    const { StepPerfForm } = await import('@/app/(app)/onboarding/_components/step-perf-form')
    render(
      <StepPerfForm defaultValues={{ garmin_synced_at: '2026-05-15T10:00:00Z' }} onDone={vi.fn()} />
    )
    expect(screen.getByText(/Synchronisé de Garmin le/)).toBeTruthy()
  })
})
