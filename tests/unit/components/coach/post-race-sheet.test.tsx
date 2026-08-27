// @vitest-environment jsdom
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PostRaceSheet } from '@/components/coach/post-race-sheet'
import type { RaceSalute } from '@/lib/coach/race-analysis'

const answerPostRacePrompt = vi.fn()
const snoozePostRacePrompt = vi.fn()

vi.mock('@/app/actions/post-race', () => ({
  answerPostRacePrompt: (...args: unknown[]) => answerPostRacePrompt(...args) as unknown,
  snoozePostRacePrompt: (...args: unknown[]) => snoozePostRacePrompt(...args) as unknown,
}))

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), info: vi.fn(), success: vi.fn() },
}))

afterEach(cleanup)

// Voir `changelog-bell.test.tsx` : jsdom n'implémente pas les Pointer Events utilisés par
// Radix Dialog, sur lequel repose Sheet.
beforeAll(() => {
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition, @typescript-eslint/unbound-method -- absent at runtime in jsdom
  Element.prototype.hasPointerCapture ??= () => false
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition, @typescript-eslint/unbound-method -- see above
  Element.prototype.setPointerCapture ??= () => undefined
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition, @typescript-eslint/unbound-method -- see above
  Element.prototype.releasePointerCapture ??= () => undefined
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition, @typescript-eslint/unbound-method -- see above
  Element.prototype.scrollIntoView ??= () => undefined
})

const CHEER: RaceSalute = {
  tone: 'cheer',
  headline: 'Objectif tenu — 4:00 sous ta cible.',
  figure: '2:25:00',
}

function renderSheet(overrides: Partial<Parameters<typeof PostRaceSheet>[0]> = {}) {
  return render(
    <PostRaceSheet
      raceGoalId="11111111-1111-4111-8111-111111111111"
      raceName="Triathlon de Vichy"
      salute={CHEER}
      surface="sheet"
      {...overrides}
    />
  )
}

describe('PostRaceSheet', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    answerPostRacePrompt.mockResolvedValue({ success: true })
    snoozePostRacePrompt.mockResolvedValue({ success: true })
  })

  it('ouvre le tiroir avec le mot sur la course et les trois caps', () => {
    renderSheet()

    expect(screen.getByText(CHEER.headline)).toBeTruthy()
    expect(screen.getByText(/2:25:00/)).toBeTruthy()
    expect(screen.getByRole('button', { name: /Maintenir ma forme/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Progresser sans objectif/ })).toBeTruthy()
    expect(screen.getByRole('link', { name: /Viser une nouvelle course/ })).toBeTruthy()
  })

  it('renvoie vers le débrief de CETTE course', () => {
    renderSheet()
    const link = screen.getByRole('link', { name: 'Voir le débrief' })
    expect(link.getAttribute('href')).toBe('/history/race/11111111-1111-4111-8111-111111111111')
  })

  it('enregistre le cap choisi et se ferme', async () => {
    const user = userEvent.setup()
    renderSheet()

    await user.click(screen.getByRole('button', { name: /Maintenir ma forme/ }))

    await waitFor(() => {
      expect(answerPostRacePrompt).toHaveBeenCalledWith(
        '11111111-1111-4111-8111-111111111111',
        'maintain'
      )
    })
    await waitFor(() => {
      expect(screen.queryByText(CHEER.headline)).toBeNull()
    })
  })

  it('reporte sans rien choisir', async () => {
    const user = userEvent.setup()
    renderSheet()

    await user.click(screen.getByRole('button', { name: 'Plus tard' }))

    await waitFor(() => {
      expect(snoozePostRacePrompt).toHaveBeenCalledWith('11111111-1111-4111-8111-111111111111')
    })
    expect(answerPostRacePrompt).not.toHaveBeenCalled()
  })

  it('reste affiché si l’enregistrement échoue', async () => {
    answerPostRacePrompt.mockResolvedValue({ success: false, error: 'save_failed' })
    const user = userEvent.setup()
    renderSheet()

    await user.click(screen.getByRole('button', { name: /Progresser sans objectif/ }))

    await waitFor(() => {
      expect(answerPostRacePrompt).toHaveBeenCalled()
    })
    // Un choix perdu en silence laisserait l'athlète croire que son cap est enregistré.
    expect(screen.getByText(CHEER.headline)).toBeTruthy()
  })

  it('en bannière : n’interrompt plus, et n’offre plus de report', () => {
    renderSheet({ surface: 'banner' })

    expect(screen.getByTestId('post-race-banner')).toBeTruthy()
    expect(screen.queryByText(CHEER.headline)).toBeNull()
    expect(screen.queryByRole('button', { name: 'Plus tard' })).toBeNull()
    expect(screen.getByRole('button', { name: /Maintenir ma forme/ })).toBeTruthy()
  })
})
