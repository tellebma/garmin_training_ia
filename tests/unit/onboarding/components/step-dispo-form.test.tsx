// @vitest-environment jsdom
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react'
import type { DispoInput } from '@/lib/onboarding/schemas'

beforeAll(() => {
  process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co'
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'anon-key-test'
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const saveStepDispo = vi.fn()
const finalizeOnboarding = vi.fn()

vi.mock('@/app/(app)/onboarding/actions', () => ({
  saveStepPerso: vi.fn(),
  saveStepRace: vi.fn(),
  saveStepPerf: vi.fn(),
  saveStepDispo: (...a: unknown[]) => saveStepDispo(...a) as unknown,
  syncGarminProfile: vi.fn(),
  finalizeOnboarding: (...a: unknown[]) => finalizeOnboarding(...a) as unknown,
}))
vi.mock('../actions', () => ({
  saveStepPerso: vi.fn(),
  saveStepRace: vi.fn(),
  saveStepPerf: vi.fn(),
  saveStepDispo: (...a: unknown[]) => saveStepDispo(...a) as unknown,
  syncGarminProfile: vi.fn(),
  finalizeOnboarding: (...a: unknown[]) => finalizeOnboarding(...a) as unknown,
}))

const toastSuccess = vi.fn()
const toastError = vi.fn()
const toastInfo = vi.fn()
const toastWarning = vi.fn()
vi.mock('sonner', () => ({
  toast: {
    success: (...a: unknown[]) => toastSuccess(...a) as unknown,
    error: (...a: unknown[]) => toastError(...a) as unknown,
    info: (...a: unknown[]) => toastInfo(...a) as unknown,
    warning: (...a: unknown[]) => toastWarning(...a) as unknown,
  },
}))

beforeEach(() => {
  saveStepDispo.mockReset()
  finalizeOnboarding.mockReset()
  toastSuccess.mockReset()
  toastError.mockReset()
  toastInfo.mockReset()
  toastWarning.mockReset()
})

const baseDefaults: DispoInput = {
  available_days: ['mon', 'wed', 'fri'],
  hours_per_week: 8,
  sports_strengths: { swim: 2, bike: 4, run: 3 },
}

describe('StepDispoForm', () => {
  it('renders with empty defaults', async () => {
    const { StepDispoForm } = await import('@/app/(app)/onboarding/_components/step-dispo-form')
    render(
      <StepDispoForm
        defaultValues={{
          available_days: undefined,
          hours_per_week: undefined,
          sports_strengths: undefined,
        }}
        onDone={vi.fn()}
      />
    )
    expect(screen.getByLabelText(/Heures par semaine/)).toBeTruthy()
    expect(screen.getByLabelText<HTMLInputElement>(/Heures par semaine/).value).toBe('')
    // 7 day buttons + submit button
    expect(screen.getByRole('button', { name: 'Lun' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Dim' })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Terminer l'onboarding/ })).toBeTruthy()
    // Default sliders should be 3/3/3
    const sliders = screen.getAllByRole<HTMLInputElement>('slider')
    const [s1, s2, s3] = sliders
    if (!s1 || !s2 || !s3) throw new Error('Expected 3 sliders')
    expect(s1.value).toBe('3')
    expect(s2.value).toBe('3')
    expect(s3.value).toBe('3')
  })

  it('renders provided default values', async () => {
    const { StepDispoForm } = await import('@/app/(app)/onboarding/_components/step-dispo-form')
    render(<StepDispoForm defaultValues={baseDefaults} onDone={vi.fn()} />)
    expect(screen.getByLabelText<HTMLInputElement>(/Heures par semaine/).value).toBe('8')
    const sliders = screen.getAllByRole<HTMLInputElement>('slider')
    const [s1, s2, s3] = sliders
    if (!s1 || !s2 || !s3) throw new Error('Expected 3 sliders')
    expect(s1.value).toBe('2')
    expect(s2.value).toBe('4')
    expect(s3.value).toBe('3')
  })

  it('toggles day buttons (add and remove)', async () => {
    const { StepDispoForm } = await import('@/app/(app)/onboarding/_components/step-dispo-form')
    render(<StepDispoForm defaultValues={baseDefaults} onDone={vi.fn()} />)
    // Mar (tue) is not in initial set → click adds it
    const mar = screen.getByRole('button', { name: 'Mar' })
    fireEvent.click(mar)
    // Lun is in the set → click removes it
    const lun = screen.getByRole('button', { name: 'Lun' })
    fireEvent.click(lun)
    // Re-toggle Mar to remove
    fireEvent.click(mar)
    expect(screen.getByRole('button', { name: 'Mar' })).toBeTruthy()
  })

  it('updates hours input', async () => {
    const { StepDispoForm } = await import('@/app/(app)/onboarding/_components/step-dispo-form')
    render(<StepDispoForm defaultValues={baseDefaults} onDone={vi.fn()} />)
    const hoursInput = screen.getByLabelText<HTMLInputElement>(/Heures par semaine/)
    fireEvent.change(hoursInput, { target: { value: '12' } })
    expect(hoursInput.value).toBe('12')
  })

  it('updates sliders (swim/bike/run)', async () => {
    const { StepDispoForm } = await import('@/app/(app)/onboarding/_components/step-dispo-form')
    render(<StepDispoForm defaultValues={baseDefaults} onDone={vi.fn()} />)
    const sliders = screen.getAllByRole<HTMLInputElement>('slider')
    const [s1, s2, s3] = sliders
    if (!s1 || !s2 || !s3) throw new Error('Expected 3 sliders')
    fireEvent.change(s1, { target: { value: '5' } })
    fireEvent.change(s2, { target: { value: '1' } })
    fireEvent.change(s3, { target: { value: '2' } })
    expect(s1.value).toBe('5')
    expect(s2.value).toBe('1')
    expect(s3.value).toBe('2')
  })

  it('submits successfully → onDone called and finalizeOnboarding triggered', async () => {
    saveStepDispo.mockResolvedValue({ success: true, nextStep: null })
    finalizeOnboarding.mockResolvedValue(undefined)
    const onDone = vi.fn()
    const { StepDispoForm } = await import('@/app/(app)/onboarding/_components/step-dispo-form')
    render(<StepDispoForm defaultValues={baseDefaults} onDone={onDone} />)
    fireEvent.click(screen.getByRole('button', { name: /Terminer l'onboarding/ }))
    await waitFor(() => {
      expect(saveStepDispo).toHaveBeenCalledTimes(1)
    })
    const call = saveStepDispo.mock.calls[0]?.[0] as Record<string, unknown>
    expect(call.available_days).toEqual(['mon', 'wed', 'fri'])
    expect(call.hours_per_week).toBe(8)
    expect(call.sports_strengths).toEqual({ swim: 2, bike: 4, run: 3 })
    await waitFor(() => {
      expect(onDone).toHaveBeenCalledWith(null)
    })
    await waitFor(() => {
      expect(finalizeOnboarding).toHaveBeenCalledTimes(1)
    })
  })

  it('shows field errors when server returns validation errors', async () => {
    saveStepDispo.mockResolvedValue({
      success: false,
      errors: { hours_per_week: ['trop haut'] },
    })
    const onDone = vi.fn()
    const { StepDispoForm } = await import('@/app/(app)/onboarding/_components/step-dispo-form')
    render(<StepDispoForm defaultValues={baseDefaults} onDone={onDone} />)
    fireEvent.click(screen.getByRole('button', { name: /Terminer l'onboarding/ }))
    await waitFor(() => {
      expect(screen.getByText('trop haut')).toBeTruthy()
    })
    expect(toastError).toHaveBeenCalledWith('Corrige les erreurs avant de continuer.')
    expect(onDone).not.toHaveBeenCalled()
    expect(finalizeOnboarding).not.toHaveBeenCalled()
  })

  it('shows generic error toast on non-validation failure', async () => {
    saveStepDispo.mockResolvedValue({ success: false, error: 'save_failed' })
    const onDone = vi.fn()
    const { StepDispoForm } = await import('@/app/(app)/onboarding/_components/step-dispo-form')
    render(<StepDispoForm defaultValues={baseDefaults} onDone={onDone} />)
    fireEvent.click(screen.getByRole('button', { name: /Terminer l'onboarding/ }))
    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith('Erreur de sauvegarde, réessaye.')
    })
    expect(onDone).not.toHaveBeenCalled()
    expect(finalizeOnboarding).not.toHaveBeenCalled()
  })

  it('shows loading state during submit (button label change)', async () => {
    let resolveSave!: (v: { success: boolean; nextStep: null }) => void
    saveStepDispo.mockReturnValue(
      new Promise((resolve) => {
        resolveSave = resolve
      })
    )
    const { StepDispoForm } = await import('@/app/(app)/onboarding/_components/step-dispo-form')
    render(<StepDispoForm defaultValues={baseDefaults} onDone={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /Terminer l'onboarding/ }))
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Finalisation/ })).toBeTruthy()
    })
    const submitBtn = screen.getByRole<HTMLButtonElement>('button', { name: /Finalisation/ })
    expect(submitBtn.disabled).toBe(true)
    resolveSave({ success: true, nextStep: null })
  })

  it('submits with empty days → available_days undefined in payload', async () => {
    saveStepDispo.mockResolvedValue({ success: true, nextStep: null })
    finalizeOnboarding.mockResolvedValue(undefined)
    const { StepDispoForm } = await import('@/app/(app)/onboarding/_components/step-dispo-form')
    render(
      <StepDispoForm
        defaultValues={{
          available_days: [],
          hours_per_week: 6,
          sports_strengths: { swim: 3, bike: 3, run: 3 },
        }}
        onDone={vi.fn()}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /Terminer l'onboarding/ }))
    await waitFor(() => {
      expect(saveStepDispo).toHaveBeenCalled()
    })
    const call = saveStepDispo.mock.calls[0]?.[0] as Record<string, unknown>
    expect(call.available_days).toBeUndefined()
    expect(call.hours_per_week).toBe(6)
  })

  it('submits with empty hours string → hours_per_week undefined in payload', async () => {
    saveStepDispo.mockResolvedValue({ success: true, nextStep: null })
    finalizeOnboarding.mockResolvedValue(undefined)
    const { StepDispoForm } = await import('@/app/(app)/onboarding/_components/step-dispo-form')
    render(
      <StepDispoForm
        defaultValues={{
          available_days: ['mon'],
          hours_per_week: undefined,
          sports_strengths: { swim: 3, bike: 3, run: 3 },
        }}
        onDone={vi.fn()}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /Terminer l'onboarding/ }))
    await waitFor(() => {
      expect(saveStepDispo).toHaveBeenCalled()
    })
    const call = saveStepDispo.mock.calls[0]?.[0] as Record<string, unknown>
    expect(call.hours_per_week).toBeUndefined()
    expect(call.available_days).toEqual(['mon'])
  })
})
