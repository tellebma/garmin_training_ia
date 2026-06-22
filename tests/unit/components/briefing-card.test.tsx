// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { BriefingCard } from '@/app/(app)/_components/briefing-card'
import { NextSessionAdjustmentActions } from '@/app/(app)/_components/next-session-adjustment-actions'
import { applySessionAdjustment, ignoreSessionAdjustment } from '@/app/actions/sessions'
import type { DailyBriefing } from '@/lib/coach/briefing-types'

vi.mock('@/app/actions/sessions', () => ({
  applySessionAdjustment: vi.fn(),
  ignoreSessionAdjustment: vi.fn(),
}))

const applyMock = vi.mocked(applySessionAdjustment)
const ignoreMock = vi.mocked(ignoreSessionAdjustment)

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('BriefingCard', () => {
  it('renders coach recommendation, session feedback and activity review insights', () => {
    const briefing: DailyBriefing = {
      date: '2026-06-15',
      readiness_score: 72,
      status: 'caution',
      explanation_md: 'Charge recente elevee, on garde de la marge.',
      factors: [],
      planned_session: null,
      suggested_session: {
        sport: 'run',
        session_type: 'endurance',
        note: 'Raccourcir la seance et rester facile.',
      },
      activity_review: {
        lookback_days: 90,
        activities_7d: 4,
        activities_28d: 14,
        tss_7d: 430,
        avg_weekly_tss_prev_21d: 280,
        elevation_gain_7d: 1200,
        avg_weekly_elevation_prev_21d: 700,
        sport_counts_28d: { run: 9, bike: 5 },
        days_since_last_activity: 1,
        insights: [
          {
            name: 'load_spike',
            severity: 'watch',
            message: 'La charge hebdo monte vite.',
            readiness_impact: -10,
          },
          {
            name: 'consistent_week',
            severity: 'positive',
            message: 'Belle regularite cette semaine.',
            readiness_impact: 4,
          },
        ],
      },
      last_session_feedback: {
        activity_date: '2026-06-14',
        sport: 'run',
        planned_sport: 'run',
        planned_session_type: 'tempo',
        verdict: 'too_intense',
        severity: 'risk',
        message: 'La derniere seance etait plus intense que prevu.',
        readiness_impact: -8,
      },
      coach_recommendation: {
        action: 'ease',
        title: 'Alleger la journee',
        rationale: 'Le cumul recent demande une seance plus facile.',
        instruction: 'Rester en endurance fondamentale.',
      },
      next_session_adjustment: {
        status: 'suggested',
        action: 'replace_with_recovery',
        title: 'Remplacer la séance dure',
        rationale: 'La derniere seance etait plus intense que prevu.',
        instruction: 'Passer en récupération active avant de reprendre le plan.',
        target_session: {
          id: 'session-1',
          sport: 'run',
          session_type: 'intervals',
          target_duration_s: 3600,
          target_tss: 75,
        },
        suggested_session_type: 'recovery',
      },
    }

    render(<BriefingCard briefing={briefing} />)

    expect(screen.getByLabelText('Briefing du jour')).toBeTruthy()
    expect(screen.getByText(/Vigilance · 72\/100/)).toBeTruthy()
    expect(screen.getByText('Alleger la journee')).toBeTruthy()
    expect(screen.getByText('Retour post-séance')).toBeTruthy()
    expect(screen.getAllByText(/plus intense que prevu/)).toHaveLength(2)
    expect(screen.getByText('Revue des activités')).toBeTruthy()
    expect(screen.getByText(/4 activités · 430 TSS · 1200 m D\+/)).toBeTruthy()
    expect(screen.getByText('La charge hebdo monte vite.')).toBeTruthy()
    expect(screen.getByText('Adaptation proposée')).toBeTruthy()
    expect(screen.getByText('Raccourcir la seance et rester facile.')).toBeTruthy()
    expect(screen.getByText('Remplacer la séance dure')).toBeTruthy()
    expect(screen.getByText(/intervals/)).toBeTruthy()
    expect(screen.getByText(/recovery/)).toBeTruthy()
    expect(screen.getByText('Accepter')).toBeTruthy()
    expect(screen.getByText('Ignorer')).toBeTruthy()
  })
})

describe('BriefingCard rest day', () => {
  it('hides the readiness badge and activity review on a rest day', () => {
    const briefing: DailyBriefing = {
      date: '2026-06-22',
      readiness_score: 88,
      status: 'ready',
      explanation_md: 'Tous les signaux sont au vert. Profite de cette journée de repos.',
      factors: [],
      planned_session: { sport: 'rest', session_type: 'rest' },
      suggested_session: null,
      activity_review: {
        lookback_days: 90,
        activities_7d: 4,
        activities_28d: 14,
        tss_7d: 430,
        avg_weekly_tss_prev_21d: 280,
        elevation_gain_7d: 1200,
        avg_weekly_elevation_prev_21d: 700,
        sport_counts_28d: { run: 9, bike: 5 },
        days_since_last_activity: 1,
        insights: [
          {
            name: 'load_spike',
            severity: 'watch',
            message: 'La charge hebdo monte vite.',
            readiness_impact: -10,
          },
        ],
      },
      last_session_feedback: null,
      coach_recommendation: {
        action: 'rest',
        title: 'Repos',
        rationale: 'Journée de récupération planifiée.',
        instruction: 'Repose-toi.',
      },
      next_session_adjustment: {
        status: 'none',
        action: 'maintain',
        title: '',
        rationale: '',
        instruction: '',
        target_session: null,
        suggested_session_type: null,
      },
      is_rest_day: true,
    }

    render(<BriefingCard briefing={briefing} />)

    // rest block is shown
    expect(screen.getByText('Jour de repos')).toBeTruthy()
    // readiness badge and activity review are hidden on a rest day
    expect(screen.queryByText(/88\/100/)).toBeNull()
    expect(screen.queryByText('Revue des activités')).toBeNull()
    expect(screen.queryByText('La charge hebdo monte vite.')).toBeNull()
  })
})

describe('NextSessionAdjustmentActions', () => {
  it('applies the suggested adjustment and confirms success', async () => {
    applyMock.mockResolvedValue({ success: true, data: { status: 'ok' } })

    render(<NextSessionAdjustmentActions sessionId="session-1" suggestedSessionType="recovery" />)
    fireEvent.click(screen.getByRole('button', { name: 'Accepter' }))

    await waitFor(() => {
      expect(applyMock).toHaveBeenCalledWith('session-1', 'recovery')
      expect(screen.getByText('Ajustement appliqué.')).toBeTruthy()
    })
  })

  it('ignores the suggestion and confirms the decision', async () => {
    ignoreMock.mockResolvedValue({ success: true, data: { status: 'ok' } })

    render(<NextSessionAdjustmentActions sessionId="session-2" suggestedSessionType="endurance" />)
    fireEvent.click(screen.getByRole('button', { name: 'Ignorer' }))

    await waitFor(() => {
      expect(ignoreMock).toHaveBeenCalledWith('session-2', 'endurance')
      expect(screen.getByText('Suggestion ignorée pour le moment.')).toBeTruthy()
    })
  })

  it('shows the action error and keeps the controls available', async () => {
    applyMock.mockResolvedValue({ success: false, error: 'session_not_found' })

    render(<NextSessionAdjustmentActions sessionId="missing" suggestedSessionType="recovery" />)
    fireEvent.click(screen.getByRole('button', { name: 'Accepter' }))

    await waitFor(() => {
      expect(screen.getByText('session_not_found')).toBeTruthy()
      expect(screen.getByRole('button', { name: 'Accepter' })).toBeTruthy()
    })
  })
})
