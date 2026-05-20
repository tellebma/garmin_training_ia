// @vitest-environment jsdom
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react'

beforeAll(() => {
  process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co'
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'anon-key-test'
})

afterEach(cleanup)

const saveStepPerso = vi.fn()

vi.mock('@/app/(app)/onboarding/actions', () => ({
  saveStepPerso: (...a: unknown[]) => saveStepPerso(...a) as unknown,
  saveStepRace: vi.fn(),
  saveStepPerf: vi.fn(),
  saveStepDispo: vi.fn(),
  syncGarminProfile: vi.fn(),
  finalizeOnboarding: vi.fn(),
}))
vi.mock('../actions', () => ({
  saveStepPerso: (...a: unknown[]) => saveStepPerso(...a) as unknown,
  saveStepRace: vi.fn(),
  saveStepPerf: vi.fn(),
  saveStepDispo: vi.fn(),
  syncGarminProfile: vi.fn(),
  finalizeOnboarding: vi.fn(),
}))

const toastSuccess = vi.fn()
const toastError = vi.fn()
const toastInfo = vi.fn()
vi.mock('sonner', () => ({
  toast: { success: toastSuccess, error: toastError, info: toastInfo, warning: vi.fn() },
}))

beforeEach(() => {
  saveStepPerso.mockReset()
  toastSuccess.mockReset()
  toastError.mockReset()
  toastInfo.mockReset()
})

describe('StepPersoForm', () => {
  it('renders all fields with empty defaults', async () => {
    const { StepPersoForm } = await import('@/app/(app)/onboarding/_components/step-perso-form')
    render(<StepPersoForm defaultValues={null} onDone={vi.fn()} />)
    expect(screen.getByLabelText(/Prénom/)).toBeTruthy()
    expect(screen.getByLabelText(/Date de naissance/)).toBeTruthy()
    expect(screen.getByLabelText(/Sexe/)).toBeTruthy()
    expect(screen.getByLabelText(/Ville/)).toBeTruthy()
    expect(screen.getByLabelText(/Pays/)).toBeTruthy()
    expect(screen.getByRole('button', { name: /Suivant/ })).toBeTruthy()
  })

  it('renders with provided default values', async () => {
    const { StepPersoForm } = await import('@/app/(app)/onboarding/_components/step-perso-form')
    render(
      <StepPersoForm
        defaultValues={{
          first_name: 'Maxime',
          dob: '1990-01-15',
          sex: 'F',
          city: 'Lille',
          country: 'France',
          consent_data_processing: true,
        }}
        onDone={vi.fn()}
      />
    )
    expect(screen.getByLabelText<HTMLInputElement>(/Prénom/).value).toBe('Maxime')
    expect(screen.getByLabelText<HTMLInputElement>(/Date de naissance/).value).toBe('1990-01-15')
    expect(screen.getByLabelText<HTMLSelectElement>(/Sexe/).value).toBe('F')
    expect(screen.getByLabelText<HTMLInputElement>(/Ville/).value).toBe('Lille')
    expect(screen.getByLabelText<HTMLInputElement>(/Pays/).value).toBe('France')
  })

  it('updates first_name when user types', async () => {
    const { StepPersoForm } = await import('@/app/(app)/onboarding/_components/step-perso-form')
    render(<StepPersoForm defaultValues={null} onDone={vi.fn()} />)
    const input = screen.getByLabelText<HTMLInputElement>(/Prénom/)
    fireEvent.change(input, { target: { value: 'Léa' } })
    expect(input.value).toBe('Léa')
  })

  it('toggles consent checkbox', async () => {
    const { StepPersoForm } = await import('@/app/(app)/onboarding/_components/step-perso-form')
    render(<StepPersoForm defaultValues={null} onDone={vi.fn()} />)
    const checkbox = screen.getByRole<HTMLInputElement>('checkbox')
    expect(checkbox.checked).toBe(false)
    fireEvent.click(checkbox)
    expect(checkbox.checked).toBe(true)
  })

  it('changes sex via the select', async () => {
    const { StepPersoForm } = await import('@/app/(app)/onboarding/_components/step-perso-form')
    render(<StepPersoForm defaultValues={null} onDone={vi.fn()} />)
    const sex = screen.getByLabelText<HTMLSelectElement>(/Sexe/)
    fireEvent.change(sex, { target: { value: 'X' } })
    expect(sex.value).toBe('X')
  })

  it('submits and calls onDone with nextStep on success', async () => {
    saveStepPerso.mockResolvedValue({ success: true, nextStep: 'race' })
    const onDone = vi.fn()
    const { StepPersoForm } = await import('@/app/(app)/onboarding/_components/step-perso-form')
    render(<StepPersoForm defaultValues={null} onDone={onDone} />)
    fireEvent.change(screen.getByLabelText(/Prénom/), { target: { value: 'Max' } })
    fireEvent.change(screen.getByLabelText(/Date de naissance/), {
      target: { value: '1990-01-15' },
    })
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: /Suivant/ }))
    await waitFor(() => {
      expect(saveStepPerso).toHaveBeenCalledTimes(1)
    })
    await waitFor(() => {
      expect(onDone).toHaveBeenCalledWith('race')
    })
  })

  it('passes optional city and country as undefined when blank', async () => {
    saveStepPerso.mockResolvedValue({ success: true, nextStep: 'race' })
    const { StepPersoForm } = await import('@/app/(app)/onboarding/_components/step-perso-form')
    render(<StepPersoForm defaultValues={null} onDone={vi.fn()} />)
    fireEvent.change(screen.getByLabelText(/Prénom/), { target: { value: 'Max' } })
    fireEvent.change(screen.getByLabelText(/Date de naissance/), {
      target: { value: '1990-01-15' },
    })
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: /Suivant/ }))
    await waitFor(() => {
      expect(saveStepPerso).toHaveBeenCalledTimes(1)
    })
    const call = saveStepPerso.mock.calls[0]?.[0] as Record<string, unknown>
    expect(call.city).toBeUndefined()
    expect(call.country).toBeUndefined()
  })

  it('displays field-level errors when server returns errors', async () => {
    saveStepPerso.mockResolvedValue({
      success: false,
      errors: {
        first_name: ['Requis'],
        dob: ['Date invalide'],
        consent_data_processing: ['Tu dois accepter'],
      },
    })
    const onDone = vi.fn()
    const { StepPersoForm } = await import('@/app/(app)/onboarding/_components/step-perso-form')
    render(<StepPersoForm defaultValues={null} onDone={onDone} />)
    fireEvent.click(screen.getByRole('button', { name: /Suivant/ }))
    await waitFor(() => {
      expect(screen.getByText(/Requis/)).toBeTruthy()
    })
    expect(screen.getByText(/Date invalide/)).toBeTruthy()
    expect(screen.getByText(/Tu dois accepter/)).toBeTruthy()
    expect(toastError).toHaveBeenCalled()
    expect(onDone).not.toHaveBeenCalled()
  })

  it('shows generic error toast when server returns a non-validation failure', async () => {
    saveStepPerso.mockResolvedValue({ success: false })
    const onDone = vi.fn()
    const { StepPersoForm } = await import('@/app/(app)/onboarding/_components/step-perso-form')
    render(<StepPersoForm defaultValues={null} onDone={onDone} />)
    fireEvent.click(screen.getByRole('button', { name: /Suivant/ }))
    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith('Erreur de sauvegarde, réessaye.')
    })
    expect(onDone).not.toHaveBeenCalled()
  })

  it('shows loading text while submitting', async () => {
    let resolvePromise!: (v: unknown) => void
    saveStepPerso.mockReturnValue(
      new Promise((r) => {
        resolvePromise = r
      })
    )
    const { StepPersoForm } = await import('@/app/(app)/onboarding/_components/step-perso-form')
    render(<StepPersoForm defaultValues={null} onDone={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /Suivant/ }))
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Sauvegarde/ })).toBeTruthy()
    })
    resolvePromise({ success: true, nextStep: 'race' })
  })
})
