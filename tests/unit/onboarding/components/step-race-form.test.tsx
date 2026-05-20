// @vitest-environment jsdom
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react'

beforeAll(() => {
  process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co'
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'anon-key-test'
})

afterEach(cleanup)

const saveStepRace = vi.fn()

vi.mock('@/app/(app)/onboarding/actions', () => ({
  saveStepPerso: vi.fn(),
  saveStepRace: (...a: unknown[]) => saveStepRace(...a) as unknown,
  saveStepPerf: vi.fn(),
  saveStepDispo: vi.fn(),
  syncGarminProfile: vi.fn(),
  finalizeOnboarding: vi.fn(),
}))
vi.mock('../actions', () => ({
  saveStepPerso: vi.fn(),
  saveStepRace: (...a: unknown[]) => saveStepRace(...a) as unknown,
  saveStepPerf: vi.fn(),
  saveStepDispo: vi.fn(),
  syncGarminProfile: vi.fn(),
  finalizeOnboarding: vi.fn(),
}))

const toastError = vi.fn()
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: toastError, info: vi.fn(), warning: vi.fn() },
}))

beforeEach(() => {
  saveStepRace.mockReset()
  toastError.mockReset()
})

describe('StepRaceForm', () => {
  it('renders with default triathlon discipline and 3 legs', async () => {
    const { StepRaceForm } = await import('@/app/(app)/onboarding/_components/step-race-form')
    render(<StepRaceForm defaultValues={null} onDone={vi.fn()} />)
    expect(screen.getByLabelText(/Date de la course/)).toBeTruthy()
    expect(screen.getByLabelText<HTMLSelectElement>(/Type de course/).value).toBe('triathlon')
    expect(screen.getByText(/3 pour Triathlon/)).toBeTruthy()
    expect(screen.getAllByText(/Natation/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Vélo/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Course/).length).toBeGreaterThan(0)
  })

  it('renders provided default values, including legs and target time', async () => {
    const { StepRaceForm } = await import('@/app/(app)/onboarding/_components/step-race-form')
    render(
      <StepRaceForm
        defaultValues={{
          race_date: '2026-09-15',
          discipline: 'triathlon',
          name: 'Iron Test',
          location: 'Nice',
          target_time_seconds: 5400, // 01:30:00
          legs: [
            { order: 1, discipline: 'swim', distance_km: 1.5, elevation_gain_m: 0 },
            { order: 2, discipline: 'bike', distance_km: 40, elevation_gain_m: 300 },
            { order: 3, discipline: 'run', distance_km: 10, elevation_gain_m: 50 },
          ],
        }}
        onDone={vi.fn()}
      />
    )
    expect(screen.getByLabelText<HTMLInputElement>(/Date de la course/).value).toBe('2026-09-15')
    expect(screen.getByLabelText<HTMLInputElement>(/Nom de la course/).value).toBe('Iron Test')
    expect(screen.getByLabelText<HTMLInputElement>(/Lieu/).value).toBe('Nice')
    expect(screen.getByLabelText<HTMLInputElement>(/Temps cible total/).value).toBe('01:30:00')
  })

  it('changes discipline and resets legs accordingly', async () => {
    const { StepRaceForm } = await import('@/app/(app)/onboarding/_components/step-race-form')
    render(<StepRaceForm defaultValues={null} onDone={vi.fn()} />)
    const select = screen.getByLabelText<HTMLSelectElement>(/Type de course/)
    fireEvent.change(select, { target: { value: 'run' } })
    expect(select.value).toBe('run')
    expect(screen.getByText(/1 pour Course/)).toBeTruthy()
  })

  it('shows the add-leg button only when discipline is autre', async () => {
    const { StepRaceForm } = await import('@/app/(app)/onboarding/_components/step-race-form')
    render(<StepRaceForm defaultValues={null} onDone={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /\+ Ajouter/ })).toBeNull()
    fireEvent.change(screen.getByLabelText(/Type de course/), { target: { value: 'autre' } })
    expect(screen.getByRole('button', { name: /\+ Ajouter/ })).toBeTruthy()
  })

  it('adds and removes legs when discipline is autre', async () => {
    const { StepRaceForm } = await import('@/app/(app)/onboarding/_components/step-race-form')
    render(<StepRaceForm defaultValues={null} onDone={vi.fn()} />)
    fireEvent.change(screen.getByLabelText(/Type de course/), { target: { value: 'autre' } })
    // initial autre: 1 leg
    fireEvent.click(screen.getByRole('button', { name: /\+ Ajouter/ }))
    fireEvent.click(screen.getByRole('button', { name: /\+ Ajouter/ }))
    // should now have 3 leg distance inputs
    expect(screen.getAllByLabelText(/^Distance/).length).toBeGreaterThanOrEqual(3)
    // there should be a remove button
    const removeBtns = screen.getAllByRole('button', { name: /− Retirer/ })
    expect(removeBtns.length).toBeGreaterThan(0)
    // remove one
    const [firstRemoveBtn] = removeBtns
    if (!firstRemoveBtn) throw new Error('Expected at least one remove button')
    fireEvent.click(firstRemoveBtn)
  })

  it('updates leg distance via input', async () => {
    const { StepRaceForm } = await import('@/app/(app)/onboarding/_components/step-race-form')
    render(<StepRaceForm defaultValues={null} onDone={vi.fn()} />)
    // First leg distance is swim
    const distInput = screen.getByLabelText('Distance (km)', { selector: '#leg-0-distance' })
    fireEvent.change(distInput, { target: { value: '1.5' } })
    expect((distInput as HTMLInputElement).value).toBe('1.5')
  })

  it('hides elevation_gain field for swim legs', async () => {
    const { StepRaceForm } = await import('@/app/(app)/onboarding/_components/step-race-form')
    render(<StepRaceForm defaultValues={null} onDone={vi.fn()} />)
    // Triathlon default: leg 0 = swim, so no leg-0-elevation input
    expect(screen.queryByLabelText('D+ (m)', { selector: '#leg-0-elevation' })).toBeNull()
    // leg 1 = bike => has elevation
    expect(screen.getByLabelText('D+ (m)', { selector: '#leg-1-elevation' })).toBeTruthy()
  })

  it('updates leg elevation via input', async () => {
    const { StepRaceForm } = await import('@/app/(app)/onboarding/_components/step-race-form')
    render(<StepRaceForm defaultValues={null} onDone={vi.fn()} />)
    const elInput = screen.getByLabelText('D+ (m)', { selector: '#leg-1-elevation' })
    fireEvent.change(elInput, { target: { value: '200' } })
    expect((elInput as HTMLInputElement).value).toBe('200')
  })

  it('allows changing a leg discipline when discipline is autre', async () => {
    const { StepRaceForm } = await import('@/app/(app)/onboarding/_components/step-race-form')
    render(<StepRaceForm defaultValues={null} onDone={vi.fn()} />)
    fireEvent.change(screen.getByLabelText(/Type de course/), { target: { value: 'autre' } })
    // The leg-discipline select is a plain select (not labelled by Label)
    const selects = screen.getAllByRole('combobox')
    // First select is Type de course, second is leg discipline
    const legDisciplineSelect = selects[1] as HTMLSelectElement
    fireEvent.change(legDisciplineSelect, { target: { value: 'bike' } })
    expect(legDisciplineSelect.value).toBe('bike')
  })

  it('submits and calls onDone with nextStep on success', async () => {
    saveStepRace.mockResolvedValue({ success: true, nextStep: 'perf' })
    const onDone = vi.fn()
    const { StepRaceForm } = await import('@/app/(app)/onboarding/_components/step-race-form')
    render(<StepRaceForm defaultValues={null} onDone={onDone} />)
    fireEvent.change(screen.getByLabelText(/Date de la course/), {
      target: { value: '2027-01-01' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Suivant/ }))
    await waitFor(() => {
      expect(saveStepRace).toHaveBeenCalledTimes(1)
    })
    await waitFor(() => {
      expect(onDone).toHaveBeenCalledWith('perf')
    })
  })

  it('parses target time hh:mm:ss into seconds', async () => {
    saveStepRace.mockResolvedValue({ success: true, nextStep: 'perf' })
    const { StepRaceForm } = await import('@/app/(app)/onboarding/_components/step-race-form')
    render(<StepRaceForm defaultValues={null} onDone={vi.fn()} />)
    fireEvent.change(screen.getByLabelText(/Date de la course/), {
      target: { value: '2027-01-01' },
    })
    fireEvent.change(screen.getByLabelText(/Temps cible total/), {
      target: { value: '01:30:45' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Suivant/ }))
    await waitFor(() => {
      expect(saveStepRace).toHaveBeenCalledTimes(1)
    })
    const call = saveStepRace.mock.calls[0]?.[0] as Record<string, unknown>
    expect(call.target_time_seconds).toBe(5445)
  })

  it('displays leg-level error messages from the server', async () => {
    saveStepRace.mockResolvedValue({
      success: false,
      errors: { legs: ['Au moins un segment requis'] },
    })
    const onDone = vi.fn()
    const { StepRaceForm } = await import('@/app/(app)/onboarding/_components/step-race-form')
    render(<StepRaceForm defaultValues={null} onDone={onDone} />)
    fireEvent.click(screen.getByRole('button', { name: /Suivant/ }))
    await waitFor(() => {
      expect(screen.getByText(/Au moins un segment requis/)).toBeTruthy()
    })
    expect(toastError).toHaveBeenCalled()
    expect(onDone).not.toHaveBeenCalled()
  })

  it('shows generic error toast when server returns a non-validation failure', async () => {
    saveStepRace.mockResolvedValue({ success: false })
    const { StepRaceForm } = await import('@/app/(app)/onboarding/_components/step-race-form')
    render(<StepRaceForm defaultValues={null} onDone={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /Suivant/ }))
    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith('Erreur de sauvegarde, réessaye.')
    })
  })

  it('updates the totals display when leg distances change', async () => {
    const { StepRaceForm } = await import('@/app/(app)/onboarding/_components/step-race-form')
    render(<StepRaceForm defaultValues={null} onDone={vi.fn()} />)
    const distInput = screen.getByLabelText('Distance (km)', { selector: '#leg-0-distance' })
    fireEvent.change(distInput, { target: { value: '1.5' } })
    expect(screen.getByText(/1\.5 km/)).toBeTruthy()
  })
})
