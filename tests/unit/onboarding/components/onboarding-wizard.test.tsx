// @vitest-environment jsdom
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, fireEvent } from '@testing-library/react'

beforeAll(() => {
  process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co'
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'anon-key-test'
})

afterEach(cleanup)

// Mock all four step forms so the wizard test isolates orchestrator behavior.
vi.mock('@/app/(app)/onboarding/_components/step-perso-form', () => ({
  StepPersoForm: ({ onDone }: { onDone: (n: string | null) => void }) => (
    <button
      type="button"
      data-testid="perso-done"
      onClick={() => {
        onDone('race')
      }}
    >
      perso-done
    </button>
  ),
}))
vi.mock('@/app/(app)/onboarding/_components/step-race-form', () => ({
  StepRaceForm: ({ onDone }: { onDone: (n: string | null) => void }) => (
    <button
      type="button"
      data-testid="race-done"
      onClick={() => {
        onDone('perf')
      }}
    >
      race-done
    </button>
  ),
}))
vi.mock('@/app/(app)/onboarding/_components/step-perf-form', () => ({
  StepPerfForm: ({ onDone }: { onDone: (n: string | null) => void }) => (
    <button
      type="button"
      data-testid="perf-done"
      onClick={() => {
        onDone('dispo')
      }}
    >
      perf-done
    </button>
  ),
}))
vi.mock('@/app/(app)/onboarding/_components/step-dispo-form', () => ({
  StepDispoForm: ({ onDone }: { onDone: (n: string | null) => void }) => (
    <button
      type="button"
      data-testid="dispo-done"
      onClick={() => {
        onDone(null)
      }}
    >
      dispo-done
    </button>
  ),
}))

interface WizardInit {
  perso: unknown
  race: unknown
  perf: {
    ftp_watts?: number
    vma_kmh?: number
    fc_max_bpm?: number
    garmin_synced_at: string | null
  }
  dispo: { hours_per_week?: number; available_days?: string[]; sports_strengths?: unknown }
}

const emptyInitial: WizardInit = {
  perso: null,
  race: null,
  perf: { garmin_synced_at: null },
  dispo: {},
}

describe('OnboardingWizard', () => {
  it('renders all four steps in the stepper nav', async () => {
    const { OnboardingWizard } =
      await import('@/app/(app)/onboarding/_components/onboarding-wizard')
    render(
      <OnboardingWizard
        initial={emptyInitial as unknown as Parameters<typeof OnboardingWizard>[0]['initial']}
        initialStep="perso"
      />
    )
    expect(screen.getByText(/Informations personnelles/)).toBeTruthy()
    expect(screen.getByText(/Course cible/)).toBeTruthy()
    expect(screen.getByText(/Performance/)).toBeTruthy()
    expect(screen.getByText(/Disponibilité/)).toBeTruthy()
  })

  it('renders the initial step content (perso by default)', async () => {
    const { OnboardingWizard } =
      await import('@/app/(app)/onboarding/_components/onboarding-wizard')
    render(
      <OnboardingWizard
        initial={emptyInitial as unknown as Parameters<typeof OnboardingWizard>[0]['initial']}
        initialStep="perso"
      />
    )
    expect(screen.getByTestId('perso-done')).toBeTruthy()
  })

  it('advances to the next step when onDone is called from a child', async () => {
    const { OnboardingWizard } =
      await import('@/app/(app)/onboarding/_components/onboarding-wizard')
    render(
      <OnboardingWizard
        initial={emptyInitial as unknown as Parameters<typeof OnboardingWizard>[0]['initial']}
        initialStep="perso"
      />
    )
    fireEvent.click(screen.getByTestId('perso-done'))
    expect(screen.getByTestId('race-done')).toBeTruthy()
  })

  it('marks completed steps and pre-marks them from initial data', async () => {
    const { OnboardingWizard } =
      await import('@/app/(app)/onboarding/_components/onboarding-wizard')
    const initial: WizardInit = {
      perso: { first_name: 'Max' },
      race: { name: 'Test' },
      perf: { ftp_watts: 250, garmin_synced_at: null },
      dispo: { hours_per_week: 8 },
    }
    render(
      <OnboardingWizard
        initial={initial as unknown as Parameters<typeof OnboardingWizard>[0]['initial']}
        initialStep="perso"
      />
    )
    // Completed non-current steps render without the "N." number prefix
    // (only their label); non-completed steps render "N. Label".
    const buttons = screen.getAllByRole('button')
    const completedButtons = buttons.filter(
      (b) =>
        !/^\d+\.\s/.test(b.textContent) &&
        /Course cible|Performance|Disponibilité/.test(b.textContent)
    )
    expect(completedButtons.length).toBeGreaterThan(0)
  })

  it('allows navigation back to a completed step via the stepper', async () => {
    const { OnboardingWizard } =
      await import('@/app/(app)/onboarding/_components/onboarding-wizard')
    render(
      <OnboardingWizard
        initial={emptyInitial as unknown as Parameters<typeof OnboardingWizard>[0]['initial']}
        initialStep="perso"
      />
    )
    // Complete perso -> go to race
    fireEvent.click(screen.getByTestId('perso-done'))
    expect(screen.getByTestId('race-done')).toBeTruthy()
    // Click on Perso button in nav (it should be reachable as completed)
    const persoBtn = screen.getByRole('button', { name: /Informations personnelles/ })
    fireEvent.click(persoBtn)
    expect(screen.getByTestId('perso-done')).toBeTruthy()
  })

  it('disables navigation to a step that is not the next allowed one', async () => {
    const { OnboardingWizard } =
      await import('@/app/(app)/onboarding/_components/onboarding-wizard')
    render(
      <OnboardingWizard
        initial={emptyInitial as unknown as Parameters<typeof OnboardingWizard>[0]['initial']}
        initialStep="perso"
      />
    )
    // Initially: only perso (current) and race (next allowed) are clickable.
    // Perf and dispo should be disabled.
    const perfBtn = screen.getByRole('button', { name: /Performance/ })
    expect((perfBtn as HTMLButtonElement).disabled).toBe(true)
    const dispoBtn = screen.getByRole('button', { name: /Disponibilité/ })
    expect((dispoBtn as HTMLButtonElement).disabled).toBe(true)
  })

  it('does not change step when clicking a disabled step button', async () => {
    const { OnboardingWizard } =
      await import('@/app/(app)/onboarding/_components/onboarding-wizard')
    render(
      <OnboardingWizard
        initial={emptyInitial as unknown as Parameters<typeof OnboardingWizard>[0]['initial']}
        initialStep="perso"
      />
    )
    const perfBtn = screen.getByRole('button', { name: /Performance/ })
    fireEvent.click(perfBtn)
    // Still on perso step
    expect(screen.getByTestId('perso-done')).toBeTruthy()
  })

  it('reaches the final step and accepts null next from dispo', async () => {
    const { OnboardingWizard } =
      await import('@/app/(app)/onboarding/_components/onboarding-wizard')
    render(
      <OnboardingWizard
        initial={emptyInitial as unknown as Parameters<typeof OnboardingWizard>[0]['initial']}
        initialStep="dispo"
      />
    )
    fireEvent.click(screen.getByTestId('dispo-done'))
    // Still on dispo step (null next means no change)
    expect(screen.getByTestId('dispo-done')).toBeTruthy()
  })

  it('renders race step when initialStep is race', async () => {
    const { OnboardingWizard } =
      await import('@/app/(app)/onboarding/_components/onboarding-wizard')
    render(
      <OnboardingWizard
        initial={emptyInitial as unknown as Parameters<typeof OnboardingWizard>[0]['initial']}
        initialStep="race"
      />
    )
    expect(screen.getByTestId('race-done')).toBeTruthy()
  })

  it('renders perf step when initialStep is perf', async () => {
    const { OnboardingWizard } =
      await import('@/app/(app)/onboarding/_components/onboarding-wizard')
    render(
      <OnboardingWizard
        initial={emptyInitial as unknown as Parameters<typeof OnboardingWizard>[0]['initial']}
        initialStep="perf"
      />
    )
    expect(screen.getByTestId('perf-done')).toBeTruthy()
  })

  it('considers perf completed when vma_kmh is provided', async () => {
    const { OnboardingWizard } =
      await import('@/app/(app)/onboarding/_components/onboarding-wizard')
    const initial: WizardInit = {
      perso: null,
      race: null,
      perf: { vma_kmh: 16.5, garmin_synced_at: null },
      dispo: {},
    }
    render(
      <OnboardingWizard
        initial={initial as unknown as Parameters<typeof OnboardingWizard>[0]['initial']}
        initialStep="perso"
      />
    )
    // Perf step should now be navigable (completed).
    const perfBtn = screen.getByRole('button', { name: /Performance/ })
    expect((perfBtn as HTMLButtonElement).disabled).toBe(false)
  })

  it('considers perf completed when fc_max_bpm is provided', async () => {
    const { OnboardingWizard } =
      await import('@/app/(app)/onboarding/_components/onboarding-wizard')
    const initial: WizardInit = {
      perso: null,
      race: null,
      perf: { fc_max_bpm: 185, garmin_synced_at: null },
      dispo: {},
    }
    render(
      <OnboardingWizard
        initial={initial as unknown as Parameters<typeof OnboardingWizard>[0]['initial']}
        initialStep="perso"
      />
    )
    const perfBtn = screen.getByRole('button', { name: /Performance/ })
    expect((perfBtn as HTMLButtonElement).disabled).toBe(false)
  })
})
