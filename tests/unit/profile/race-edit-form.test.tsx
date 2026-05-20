// @vitest-environment jsdom
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react'
import type { RaceInput } from '@/lib/onboarding/schemas'

beforeAll(() => {
  process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co'
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'anon-key-test'
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const saveStepRace = vi.fn()

const toastSuccess = vi.fn()
const toastError = vi.fn()
const toastInfo = vi.fn()
const toastWarning = vi.fn()

vi.mock('@/app/(app)/onboarding/actions', () => ({
  saveStepPerso: vi.fn(),
  saveStepRace: (...a: unknown[]) => saveStepRace(...a) as unknown,
  saveStepPerf: vi.fn(),
  saveStepDispo: vi.fn(),
  syncGarminProfile: vi.fn(),
  finalizeOnboarding: vi.fn(),
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

beforeEach(() => {
  saveStepRace.mockReset()
  toastSuccess.mockReset()
  toastError.mockReset()
})

const baseTriathlon: RaceInput = {
  race_date: '2027-09-15',
  discipline: 'triathlon',
  name: 'Ironman Test',
  location: 'Nice',
  target_time_seconds: 5400, // 01:30:00
  legs: [
    { order: 1, discipline: 'swim', distance_km: 1.5, elevation_gain_m: 0 },
    { order: 2, discipline: 'bike', distance_km: 40, elevation_gain_m: 300 },
    { order: 3, discipline: 'run', distance_km: 10, elevation_gain_m: 50 },
  ],
}

describe('RaceEditForm — view mode', () => {
  it('renders read-only summary with initial data', async () => {
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    render(<RaceEditForm initial={baseTriathlon} />)
    expect(screen.getByRole('heading', { name: /Course cible/ })).toBeTruthy()
    expect(screen.getByText(/Ironman Test/)).toBeTruthy()
    expect(screen.getByText(/2027-09-15/)).toBeTruthy()
    expect(screen.getByText(/Total :/)).toBeTruthy()
    expect(screen.getByText(/Cible : 01:30:00/)).toBeTruthy()
    expect(screen.getByRole('button', { name: /Modifier/ })).toBeTruthy()
  })

  it('uses discipline label when name is missing', async () => {
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    const initial: RaceInput = { ...baseTriathlon, name: undefined }
    render(<RaceEditForm initial={initial} />)
    expect(screen.getByText(/Triathlon/)).toBeTruthy()
  })

  it('renders an Ajouter link when initial is null', async () => {
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    render(<RaceEditForm initial={null} />)
    expect(screen.getByText(/Pas de course définie/)).toBeTruthy()
    const link = screen.getByRole('link', { name: /Ajouter/ })
    expect(link).toBeTruthy()
    expect(link.getAttribute('href')).toBe('/onboarding')
  })

  it('does not show target time when target_time_seconds is undefined', async () => {
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    const initial: RaceInput = { ...baseTriathlon, target_time_seconds: undefined }
    render(<RaceEditForm initial={initial} />)
    expect(screen.queryByText(/Cible :/)).toBeNull()
  })
})

describe('RaceEditForm — switch to edit mode', () => {
  it('switches to edit mode after clicking Modifier', async () => {
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    render(<RaceEditForm initial={baseTriathlon} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    expect(screen.getByRole('heading', { name: /Course cible — édition/ })).toBeTruthy()
    expect(screen.getByLabelText(/Date/)).toBeTruthy()
    expect(screen.getByLabelText(/Type/)).toBeTruthy()
    expect(screen.getByRole('button', { name: /Enregistrer/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Annuler/ })).toBeTruthy()
  })

  it('pre-fills inputs in edit mode with initial values', async () => {
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    render(<RaceEditForm initial={baseTriathlon} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    expect(screen.getByLabelText<HTMLInputElement>(/Date/).value).toBe('2027-09-15')
    expect(screen.getByLabelText<HTMLInputElement>(/Nom/).value).toBe('Ironman Test')
    expect(screen.getByLabelText<HTMLInputElement>(/Lieu/).value).toBe('Nice')
    expect(screen.getByLabelText<HTMLInputElement>(/Temps cible/).value).toBe('01:30:00')
  })
})

describe('RaceEditForm — discipline switching', () => {
  it('switches discipline to run and resets legs to a single run leg', async () => {
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    render(<RaceEditForm initial={baseTriathlon} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    const typeSelect = screen.getByLabelText<HTMLSelectElement>(/Type/)
    fireEvent.change(typeSelect, { target: { value: 'run' } })
    expect(typeSelect.value).toBe('run')
    // Only one distance input remains (single leg)
    const distanceInputs = screen.getAllByLabelText(/Distance \(km\)/)
    expect(distanceInputs.length).toBe(1)
  })

  it('switches to autre and shows the add-leg button', async () => {
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    render(<RaceEditForm initial={baseTriathlon} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.change(screen.getByLabelText(/Type/), { target: { value: 'autre' } })
    expect(screen.getByRole('button', { name: /\+ Ajouter/ })).toBeTruthy()
  })

  it('preserves matching sequence legs when switching to a discipline that matches existing legs', async () => {
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    render(<RaceEditForm initial={baseTriathlon} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    // Triathlon legs already match swim/bike/run, switching to triathlon again should preserve them
    const select = screen.getByLabelText<HTMLSelectElement>(/Type/)
    fireEvent.change(select, { target: { value: 'triathlon' } })
    // Still 3 legs
    expect(screen.getAllByLabelText(/Distance \(km\)/).length).toBe(3)
    // Distances preserved
    const distanceInputs = screen.getAllByLabelText<HTMLInputElement>(/Distance \(km\)/)
    const [swimDist] = distanceInputs
    if (!swimDist) throw new Error('Expected swim distance input')
    expect(swimDist.value).toBe('1.5')
  })

  it('hides elevation field for swim legs but shows it for bike/run legs', async () => {
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    render(<RaceEditForm initial={baseTriathlon} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    // Leg 0 = swim → no D+ input
    expect(screen.queryByLabelText('D+ (m)', { selector: '#re-leg-0-e' })).toBeNull()
    // Leg 1 = bike → has D+ input
    expect(screen.getByLabelText('D+ (m)', { selector: '#re-leg-1-e' })).toBeTruthy()
    // Leg 2 = run → has D+ input
    expect(screen.getByLabelText('D+ (m)', { selector: '#re-leg-2-e' })).toBeTruthy()
  })
})

describe('RaceEditForm — editing fields', () => {
  it('edits date, name, location and target time', async () => {
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    render(<RaceEditForm initial={baseTriathlon} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))

    const dateInput = screen.getByLabelText<HTMLInputElement>(/Date/)
    fireEvent.change(dateInput, { target: { value: '2028-01-01' } })
    expect(dateInput.value).toBe('2028-01-01')

    const nameInput = screen.getByLabelText<HTMLInputElement>(/Nom/)
    fireEvent.change(nameInput, { target: { value: 'New Race' } })
    expect(nameInput.value).toBe('New Race')

    const locationInput = screen.getByLabelText<HTMLInputElement>(/Lieu/)
    fireEvent.change(locationInput, { target: { value: 'Paris' } })
    expect(locationInput.value).toBe('Paris')

    const targetInput = screen.getByLabelText<HTMLInputElement>(/Temps cible/)
    fireEvent.change(targetInput, { target: { value: '05:30:00' } })
    expect(targetInput.value).toBe('05:30:00')
  })

  it('updates a leg distance value', async () => {
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    render(<RaceEditForm initial={baseTriathlon} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    const swimDist = screen.getByLabelText('Distance (km)', { selector: '#re-leg-0-d' })
    fireEvent.change(swimDist, { target: { value: '2.5' } })
    expect((swimDist as HTMLInputElement).value).toBe('2.5')
  })

  it('updates a leg elevation value', async () => {
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    render(<RaceEditForm initial={baseTriathlon} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    const bikeEl = screen.getByLabelText('D+ (m)', { selector: '#re-leg-1-e' })
    fireEvent.change(bikeEl, { target: { value: '500' } })
    expect((bikeEl as HTMLInputElement).value).toBe('500')
  })

  it('handles non-numeric input on distance gracefully', async () => {
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    render(<RaceEditForm initial={baseTriathlon} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    const swimDist = screen.getByLabelText('Distance (km)', { selector: '#re-leg-0-d' })
    fireEvent.change(swimDist, { target: { value: 'abc' } })
    // Falls back to 0 → input shows empty (because `value={leg.distance_km || ''}`)
    expect((swimDist as HTMLInputElement).value).toBe('')
  })

  it('handles non-numeric input on elevation gracefully', async () => {
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    render(<RaceEditForm initial={baseTriathlon} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    const bikeEl = screen.getByLabelText('D+ (m)', { selector: '#re-leg-1-e' })
    fireEvent.change(bikeEl, { target: { value: 'xyz' } })
    expect((bikeEl as HTMLInputElement).value).toBe('')
  })

  it('updates total display when leg distance changes', async () => {
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    render(<RaceEditForm initial={baseTriathlon} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    const swimDist = screen.getByLabelText('Distance (km)', { selector: '#re-leg-0-d' })
    fireEvent.change(swimDist, { target: { value: '3' } })
    // Total = 3 + 40 + 10 = 53.0 km
    expect(screen.getByText(/53\.0 km/)).toBeTruthy()
  })
})

describe('RaceEditForm — autre discipline (add/remove legs)', () => {
  it('changes a leg discipline via the leg select when discipline is autre', async () => {
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    render(<RaceEditForm initial={baseTriathlon} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.change(screen.getByLabelText(/Type/), { target: { value: 'autre' } })
    // First select is "Type" (re-discipline), subsequent ones are leg discipline selects
    const selects = screen.getAllByRole('combobox')
    const legSelect = selects[1]
    if (!legSelect) throw new Error('Expected at least one leg discipline select')
    fireEvent.change(legSelect, { target: { value: 'bike' } })
    expect((legSelect as HTMLSelectElement).value).toBe('bike')
  })

  it('forces elevation_gain_m to 0 when leg discipline switched to swim', async () => {
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    render(<RaceEditForm initial={baseTriathlon} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.change(screen.getByLabelText(/Type/), { target: { value: 'autre' } })
    // In autre mode, first leg is swim with elevation 0 already, switch leg 2 (bike, has 300 D+) to swim
    const selects = screen.getAllByRole('combobox')
    // selects[0] = type, selects[1] = leg 0 disc, selects[2] = leg 1 disc, selects[3] = leg 2 disc
    const leg1DiscSelect = selects[2]
    if (!leg1DiscSelect) throw new Error('Expected leg 1 discipline select')
    fireEvent.change(leg1DiscSelect, { target: { value: 'swim' } })
    // After switch to swim, the bike-elevation input should disappear
    expect(screen.queryByLabelText('D+ (m)', { selector: '#re-leg-1-e' })).toBeNull()
  })

  it('adds a new leg when clicking + Ajouter (discipline=autre)', async () => {
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    render(<RaceEditForm initial={baseTriathlon} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.change(screen.getByLabelText(/Type/), { target: { value: 'autre' } })
    const before = screen.getAllByLabelText(/Distance \(km\)/).length
    fireEvent.click(screen.getByRole('button', { name: /\+ Ajouter/ }))
    const after = screen.getAllByLabelText(/Distance \(km\)/).length
    expect(after).toBe(before + 1)
  })

  it('removes a leg when clicking − Retirer (discipline=autre, more than 1 leg)', async () => {
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    render(<RaceEditForm initial={baseTriathlon} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.change(screen.getByLabelText(/Type/), { target: { value: 'autre' } })
    const before = screen.getAllByLabelText(/Distance \(km\)/).length
    const removeButtons = screen.getAllByRole('button', { name: /− Retirer/ })
    const [firstRemove] = removeButtons
    if (!firstRemove) throw new Error('Expected at least one remove button')
    fireEvent.click(firstRemove)
    const after = screen.getAllByLabelText(/Distance \(km\)/).length
    expect(after).toBe(before - 1)
  })

  it('hides remove button when only one leg remains', async () => {
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    // Start with a discipline that has only 1 leg by default (run)
    const singleLeg: RaceInput = {
      race_date: '2027-09-15',
      discipline: 'run',
      name: 'Marathon',
      legs: [{ order: 1, discipline: 'run', distance_km: 42, elevation_gain_m: 0 }],
    }
    render(<RaceEditForm initial={singleLeg} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.change(screen.getByLabelText(/Type/), { target: { value: 'autre' } })
    // Only 1 leg → no remove button
    expect(screen.queryByRole('button', { name: /− Retirer/ })).toBeNull()
  })

  it('disables + Ajouter button when reaching 10 legs', async () => {
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    render(<RaceEditForm initial={baseTriathlon} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.change(screen.getByLabelText(/Type/), { target: { value: 'autre' } })
    // We start with 3 legs (triathlon) and need to go to 10 → click + Ajouter 7 times
    for (let i = 0; i < 7; i += 1) {
      fireEvent.click(screen.getByRole('button', { name: /\+ Ajouter/ }))
    }
    const addBtn = screen.getByRole<HTMLButtonElement>('button', { name: /\+ Ajouter/ })
    expect(addBtn.disabled).toBe(true)
  })
})

describe('RaceEditForm — submit / cancel / errors', () => {
  it('submits the form successfully and exits edit mode', async () => {
    saveStepRace.mockResolvedValueOnce({ success: true, nextStep: null })
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    render(<RaceEditForm initial={baseTriathlon} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.click(screen.getByRole('button', { name: /Enregistrer/ }))
    await waitFor(() => {
      expect(saveStepRace).toHaveBeenCalledTimes(1)
    })
    await waitFor(() => {
      expect(toastSuccess).toHaveBeenCalled()
    })
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Modifier/ })).toBeTruthy()
    })
  })

  it('parses target time hh:mm:ss into seconds on submit', async () => {
    saveStepRace.mockResolvedValueOnce({ success: true, nextStep: null })
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    render(<RaceEditForm initial={baseTriathlon} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    const targetInput = screen.getByLabelText(/Temps cible/)
    fireEvent.change(targetInput, { target: { value: '02:15:30' } })
    fireEvent.click(screen.getByRole('button', { name: /Enregistrer/ }))
    await waitFor(() => {
      expect(saveStepRace).toHaveBeenCalledTimes(1)
    })
    const call = saveStepRace.mock.calls[0]?.[0] as Record<string, unknown>
    expect(call.target_time_seconds).toBe(2 * 3600 + 15 * 60 + 30)
  })

  it('sends undefined target_time_seconds when target is empty', async () => {
    saveStepRace.mockResolvedValueOnce({ success: true, nextStep: null })
    const initial: RaceInput = { ...baseTriathlon, target_time_seconds: undefined }
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    render(<RaceEditForm initial={initial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.click(screen.getByRole('button', { name: /Enregistrer/ }))
    await waitFor(() => {
      expect(saveStepRace).toHaveBeenCalledTimes(1)
    })
    const call = saveStepRace.mock.calls[0]?.[0] as Record<string, unknown>
    expect(call.target_time_seconds).toBeUndefined()
  })

  it('sends undefined name and location when empty', async () => {
    saveStepRace.mockResolvedValueOnce({ success: true, nextStep: null })
    const initial: RaceInput = { ...baseTriathlon, name: undefined, location: undefined }
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    render(<RaceEditForm initial={initial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.click(screen.getByRole('button', { name: /Enregistrer/ }))
    await waitFor(() => {
      expect(saveStepRace).toHaveBeenCalledTimes(1)
    })
    const call = saveStepRace.mock.calls[0]?.[0] as Record<string, unknown>
    expect(call.name).toBeUndefined()
    expect(call.location).toBeUndefined()
  })

  it('shows toast.error and stays in edit mode on action failure', async () => {
    saveStepRace.mockResolvedValueOnce({ success: false, error: 'unauthenticated' })
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    render(<RaceEditForm initial={baseTriathlon} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.click(screen.getByRole('button', { name: /Enregistrer/ }))
    await waitFor(() => {
      expect(toastError).toHaveBeenCalled()
    })
    // Stays in edit mode
    expect(screen.getByRole('button', { name: /Enregistrer/ })).toBeTruthy()
    expect(toastSuccess).not.toHaveBeenCalled()
  })

  it('shows toast.error and stays in edit mode when errors map is returned', async () => {
    saveStepRace.mockResolvedValueOnce({
      success: false,
      errors: { legs: ['Au moins un segment requis'] },
    })
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    render(<RaceEditForm initial={baseTriathlon} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.click(screen.getByRole('button', { name: /Enregistrer/ }))
    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith('Erreur de sauvegarde')
    })
    expect(screen.getByRole('button', { name: /Enregistrer/ })).toBeTruthy()
  })

  it('Annuler reverts to view mode without calling the action', async () => {
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    render(<RaceEditForm initial={baseTriathlon} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.change(screen.getByLabelText(/Nom/), { target: { value: 'Changed Name' } })
    fireEvent.click(screen.getByRole('button', { name: /Annuler/ }))
    expect(saveStepRace).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: /Modifier/ })).toBeTruthy()
  })

  it('shows loading state during submission', async () => {
    let resolveAction: ((value: { success: boolean }) => void) | undefined
    saveStepRace.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveAction = resolve
      })
    )
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    render(<RaceEditForm initial={baseTriathlon} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.click(screen.getByRole('button', { name: /Enregistrer/ }))
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Sauvegarde/ })).toBeTruthy()
    })
    if (!resolveAction) throw new Error('resolveAction not assigned')
    resolveAction({ success: true })
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Modifier/ })).toBeTruthy()
    })
  })

  it('handles initial = null switch path (defaults to triathlon discipline and legs)', async () => {
    // Even though initial=null hides the edit button, we can verify the default state via switching
    // an initial with discipline=run and ensuring switch back to triathlon resets legs.
    const initial: RaceInput = {
      race_date: '2027-09-15',
      discipline: 'run',
      legs: [{ order: 1, discipline: 'run', distance_km: 42, elevation_gain_m: 0 }],
    }
    const { RaceEditForm } = await import('@/app/(app)/profile/_components/race-edit-form')
    render(<RaceEditForm initial={initial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.change(screen.getByLabelText(/Type/), { target: { value: 'triathlon' } })
    // Should now have 3 legs
    expect(screen.getAllByLabelText(/Distance \(km\)/).length).toBe(3)
  })
})
