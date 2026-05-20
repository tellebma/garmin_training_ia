// @vitest-environment jsdom
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
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

const baseInitial: DispoInput = {
  available_days: ['mon', 'wed', 'fri'],
  hours_per_week: 8,
  sports_strengths: { swim: 2, bike: 4, run: 3 },
}

describe('DispoEditForm', () => {
  it('renders read-only summary with initial data', async () => {
    const { DispoEditForm } = await import('@/app/(app)/profile/_components/dispo-edit-form')
    render(<DispoEditForm initial={baseInitial} />)
    expect(screen.getByRole('heading', { name: /Disponibilité/ })).toBeTruthy()
    expect(screen.getByText(/Lun, Mer, Ven/)).toBeTruthy()
    expect(screen.getByText(/8 h/)).toBeTruthy()
    expect(screen.getByText('2 / 4 / 3')).toBeTruthy()
    expect(screen.getByRole('button', { name: /Modifier/ })).toBeTruthy()
  })

  it('shows em-dashes when initial values are empty', async () => {
    const { DispoEditForm } = await import('@/app/(app)/profile/_components/dispo-edit-form')
    render(
      <DispoEditForm
        initial={{
          available_days: undefined,
          hours_per_week: undefined,
          sports_strengths: undefined,
        }}
      />
    )
    // Defaults filled silently in state; verify hours em-dash
    const hours = screen.getAllByText('—')
    expect(hours.length).toBeGreaterThan(0)
  })

  it('switches to edit mode after clicking Modifier', async () => {
    const { DispoEditForm } = await import('@/app/(app)/profile/_components/dispo-edit-form')
    render(<DispoEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    expect(screen.getByLabelText(/Heures par semaine/)).toBeTruthy()
    expect(screen.getByRole('button', { name: /Enregistrer/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Annuler/ })).toBeTruthy()
  })

  it('toggles day buttons in edit mode', async () => {
    const { DispoEditForm } = await import('@/app/(app)/profile/_components/dispo-edit-form')
    render(<DispoEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    // Mar (tue) is not in the initial set → click adds it
    const mar = screen.getByRole('button', { name: 'Mar' })
    fireEvent.click(mar)
    // Lun is in the set → click removes it
    const lun = screen.getByRole('button', { name: 'Lun' })
    fireEvent.click(lun)
    // Re-click Mar to remove
    fireEvent.click(mar)
    expect(screen.getByRole('button', { name: 'Mar' })).toBeTruthy()
  })

  it('updates inputs (hours and sliders)', async () => {
    const { DispoEditForm } = await import('@/app/(app)/profile/_components/dispo-edit-form')
    render(<DispoEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    const hoursInput = screen.getByLabelText<HTMLInputElement>(/Heures par semaine/)
    fireEvent.change(hoursInput, { target: { value: '12' } })
    expect(hoursInput.value).toBe('12')

    const sliders = screen.getAllByRole('slider')
    const [s1, s2, s3] = sliders
    if (!s1 || !s2 || !s3) throw new Error('Expected 3 sliders')
    fireEvent.change(s1, { target: { value: '5' } })
    fireEvent.change(s2, { target: { value: '1' } })
    fireEvent.change(s3, { target: { value: '2' } })
  })

  it('Annuler reverts edit mode and does not call the action', async () => {
    const { DispoEditForm } = await import('@/app/(app)/profile/_components/dispo-edit-form')
    render(<DispoEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    const hoursInput = screen.getByLabelText(/Heures par semaine/)
    fireEvent.change(hoursInput, { target: { value: '20' } })
    fireEvent.click(screen.getByRole('button', { name: /Annuler/ }))
    expect(saveStepDispo).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: /Modifier/ })).toBeTruthy()
  })

  it('submits the form successfully and exits edit mode', async () => {
    saveStepDispo.mockResolvedValueOnce({ success: true, nextStep: null })
    const { DispoEditForm } = await import('@/app/(app)/profile/_components/dispo-edit-form')
    render(<DispoEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.click(screen.getByRole('button', { name: /Enregistrer/ }))
    await waitFor(() => {
      expect(saveStepDispo).toHaveBeenCalledTimes(1)
    })
    await waitFor(() => {
      expect(toastSuccess).toHaveBeenCalled()
    })
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Modifier/ })).toBeTruthy()
    })
  })

  it('shows toast.error on Server Action failure', async () => {
    saveStepDispo.mockResolvedValueOnce({ success: false, error: 'unauthenticated' })
    const { DispoEditForm } = await import('@/app/(app)/profile/_components/dispo-edit-form')
    render(<DispoEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.click(screen.getByRole('button', { name: /Enregistrer/ }))
    await waitFor(() => {
      expect(toastError).toHaveBeenCalled()
    })
    // Stays in edit mode
    expect(screen.getByRole('button', { name: /Enregistrer/ })).toBeTruthy()
  })

  it('renders field errors when action returns errors map', async () => {
    saveStepDispo.mockResolvedValueOnce({
      success: false,
      errors: { hours_per_week: ['trop haut'] },
    })
    const { DispoEditForm } = await import('@/app/(app)/profile/_components/dispo-edit-form')
    render(<DispoEditForm initial={baseInitial} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.click(screen.getByRole('button', { name: /Enregistrer/ }))
    await waitFor(() => {
      expect(screen.getByText('trop haut')).toBeTruthy()
    })
  })

  it('submits with empty days → undefined payload field', async () => {
    saveStepDispo.mockResolvedValueOnce({ success: true })
    const { DispoEditForm } = await import('@/app/(app)/profile/_components/dispo-edit-form')
    render(<DispoEditForm initial={{ ...baseInitial, available_days: [] }} />)
    fireEvent.click(screen.getByRole('button', { name: /Modifier/ }))
    fireEvent.click(screen.getByRole('button', { name: /Enregistrer/ }))
    await waitFor(() => {
      expect(saveStepDispo).toHaveBeenCalled()
    })
    const call = saveStepDispo.mock.calls[0]?.[0] as Record<string, unknown>
    expect(call.available_days).toBeUndefined()
  })
})
