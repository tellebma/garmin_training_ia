// @vitest-environment jsdom
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react'
import type { PersonInput } from '@/lib/onboarding/schemas'

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

const baseInitial: PersonInput = {
  first_name: 'Maxime',
  dob: '1990-01-15',
  sex: 'M',
  city: 'Lille',
  country: 'France',
  consent_data_processing: true,
}

describe('PersoEditForm', () => {
  it('renders read-only summary with initial data', async () => {
    const { PersoEditForm } = await import('@/app/(app)/profile/_components/perso-edit-form')
    render(<PersoEditForm initial={baseInitial} />)
    expect(screen.getByRole('heading', { name: /Informations personnelles/ })).toBeTruthy()
    expect(screen.getByText(/Maxime/)).toBeTruthy()
    expect(screen.getByText(/1990-01-15/)).toBeTruthy()
    expect(screen.getByText(/Lille, France/)).toBeTruthy()
    expect(screen.getByRole('button', { name: /Modifier/ })).toBeTruthy()
  })

  it('renders summary without city/country when both empty', async () => {
    const { PersoEditForm } = await import('@/app/(app)/profile/_components/perso-edit-form')
    render(
      <PersoEditForm
        initial={{
          first_name: 'Léa',
          dob: '1992-06-20',
          sex: 'F',
          consent_data_processing: true,
        }}
      />
    )
    expect(screen.getByText(/Léa · 1992-06-20 · F/)).toBeTruthy()
    // No comma should appear since city/country are both empty
    expect(screen.queryByText(/,/)).toBeNull()
  })

  it('renders summary with em-dash when only city is set', async () => {
    const { PersoEditForm } = await import('@/app/(app)/profile/_components/perso-edit-form')
    render(
      <PersoEditForm
        initial={{
          first_name: 'Léa',
          dob: '1992-06-20',
          sex: 'F',
          city: 'Paris',
          consent_data_processing: true,
        }}
      />
    )
    expect(screen.getByText(/Paris, —/)).toBeTruthy()
  })

  it('switches to edit mode after clicking Modifier', async () => {
    const { PersoEditForm } = await import('@/app/(app)/profile/_components/perso-edit-form')
    render(<PersoEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    expect(screen.getByLabelText(/Prénom/)).toBeTruthy()
    expect(screen.getByLabelText(/Date de naissance/)).toBeTruthy()
    expect(screen.getByLabelText(/Sexe/)).toBeTruthy()
    expect(screen.getByLabelText(/Ville/)).toBeTruthy()
    expect(screen.getByLabelText(/Pays/)).toBeTruthy()
    expect(screen.getByRole('checkbox')).toBeTruthy()
    expect(screen.getByRole('button', { name: /Enregistrer/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Annuler/ })).toBeTruthy()
  })

  it('updates each text field in edit mode', async () => {
    const { PersoEditForm } = await import('@/app/(app)/profile/_components/perso-edit-form')
    render(<PersoEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))

    const firstName = screen.getByLabelText<HTMLInputElement>(/Prénom/)
    fireEvent.change(firstName, { target: { value: 'Léa' } })
    expect(firstName.value).toBe('Léa')

    const dob = screen.getByLabelText<HTMLInputElement>(/Date de naissance/)
    fireEvent.change(dob, { target: { value: '1992-06-20' } })
    expect(dob.value).toBe('1992-06-20')

    const sex = screen.getByLabelText<HTMLSelectElement>(/Sexe/)
    fireEvent.change(sex, { target: { value: 'X' } })
    expect(sex.value).toBe('X')

    const city = screen.getByLabelText<HTMLInputElement>(/Ville/)
    fireEvent.change(city, { target: { value: 'Paris' } })
    expect(city.value).toBe('Paris')

    const country = screen.getByLabelText<HTMLInputElement>(/Pays/)
    fireEvent.change(country, { target: { value: 'Belgique' } })
    expect(country.value).toBe('Belgique')
  })

  it('toggles consent checkbox in edit mode', async () => {
    const { PersoEditForm } = await import('@/app/(app)/profile/_components/perso-edit-form')
    render(<PersoEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    const checkbox = screen.getByRole<HTMLInputElement>('checkbox')
    expect(checkbox.checked).toBe(true)
    fireEvent.click(checkbox)
    expect(checkbox.checked).toBe(false)
    fireEvent.click(checkbox)
    expect(checkbox.checked).toBe(true)
  })

  it('Annuler reverts changes and exits edit mode', async () => {
    const { PersoEditForm } = await import('@/app/(app)/profile/_components/perso-edit-form')
    render(<PersoEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    const firstName = screen.getByLabelText<HTMLInputElement>(/Prénom/)
    fireEvent.change(firstName, { target: { value: 'Bob' } })
    fireEvent.click(screen.getByRole('button', { name: /Annuler/ }))
    expect(saveStepPerso).not.toHaveBeenCalled()
    // Back in view mode
    expect(screen.getByRole('button', { name: /Modifier/ })).toBeTruthy()
    // Re-open edit → value should be reset to initial
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    expect(screen.getByLabelText<HTMLInputElement>(/Prénom/).value).toBe('Maxime')
  })

  it('submits the form successfully and exits edit mode', async () => {
    saveStepPerso.mockResolvedValueOnce({ success: true, nextStep: null })
    const { PersoEditForm } = await import('@/app/(app)/profile/_components/perso-edit-form')
    render(<PersoEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.click(screen.getByRole('button', { name: /Enregistrer/ }))
    await waitFor(() => {
      expect(saveStepPerso).toHaveBeenCalledTimes(1)
    })
    await waitFor(() => {
      expect(toastSuccess).toHaveBeenCalled()
    })
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Modifier/ })).toBeTruthy()
    })
  })

  it('shows toast.error on Server Action failure without errors map', async () => {
    saveStepPerso.mockResolvedValueOnce({ success: false })
    const { PersoEditForm } = await import('@/app/(app)/profile/_components/perso-edit-form')
    render(<PersoEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.click(screen.getByRole('button', { name: /Enregistrer/ }))
    await waitFor(() => {
      expect(toastError).toHaveBeenCalled()
    })
    // Stays in edit mode
    expect(screen.getByRole('button', { name: /Enregistrer/ })).toBeTruthy()
  })

  it('renders field-level errors when action returns errors map', async () => {
    saveStepPerso.mockResolvedValueOnce({
      success: false,
      errors: {
        first_name: ['Requis'],
        dob: ['Date invalide'],
        consent_data_processing: ['Tu dois accepter'],
      },
    })
    const { PersoEditForm } = await import('@/app/(app)/profile/_components/perso-edit-form')
    render(<PersoEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.click(screen.getByRole('button', { name: /Enregistrer/ }))
    await waitFor(() => {
      expect(screen.getByText(/Requis/)).toBeTruthy()
    })
    expect(screen.getByText(/Date invalide/)).toBeTruthy()
    expect(screen.getByText(/Tu dois accepter/)).toBeTruthy()
    // No global toast.error when field errors are present
    expect(toastError).not.toHaveBeenCalled()
    // Stays in edit mode
    expect(screen.getByRole('button', { name: /Enregistrer/ })).toBeTruthy()
  })

  it('converts blank city/country to undefined in payload', async () => {
    saveStepPerso.mockResolvedValueOnce({ success: true })
    const { PersoEditForm } = await import('@/app/(app)/profile/_components/perso-edit-form')
    render(<PersoEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    const city = screen.getByLabelText<HTMLInputElement>(/Ville/)
    const country = screen.getByLabelText<HTMLInputElement>(/Pays/)
    fireEvent.change(city, { target: { value: '' } })
    fireEvent.change(country, { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: /Enregistrer/ }))
    await waitFor(() => {
      expect(saveStepPerso).toHaveBeenCalledTimes(1)
    })
    const firstCall = saveStepPerso.mock.calls[0]
    if (!firstCall) throw new Error('Expected saveStepPerso to be called')
    const payload = firstCall[0] as Record<string, unknown>
    expect(payload.city).toBeUndefined()
    expect(payload.country).toBeUndefined()
  })

  it('shows loading text while submitting', async () => {
    let resolvePromise!: (v: unknown) => void
    saveStepPerso.mockReturnValueOnce(
      new Promise((r) => {
        resolvePromise = r
      })
    )
    const { PersoEditForm } = await import('@/app/(app)/profile/_components/perso-edit-form')
    render(<PersoEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.click(screen.getByRole('button', { name: /Enregistrer/ }))
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Sauvegarde/ })).toBeTruthy()
    })
    // Annuler button is also disabled while loading
    const cancel = screen.getByRole<HTMLButtonElement>('button', { name: /Annuler/ })
    expect(cancel.disabled).toBe(true)
    resolvePromise({ success: true })
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Modifier/ })).toBeTruthy()
    })
  })

  it('clears previous errors before re-submission', async () => {
    saveStepPerso
      .mockResolvedValueOnce({
        success: false,
        errors: { first_name: ['Requis'] },
      })
      .mockResolvedValueOnce({ success: true })
    const { PersoEditForm } = await import('@/app/(app)/profile/_components/perso-edit-form')
    render(<PersoEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.click(screen.getByRole('button', { name: /Enregistrer/ }))
    await waitFor(() => {
      expect(screen.getByText(/Requis/)).toBeTruthy()
    })
    fireEvent.click(screen.getByRole('button', { name: /Enregistrer/ }))
    await waitFor(() => {
      expect(saveStepPerso).toHaveBeenCalledTimes(2)
    })
    await waitFor(() => {
      expect(screen.queryByText(/Requis/)).toBeNull()
    })
  })
})
