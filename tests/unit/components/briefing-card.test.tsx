// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { BriefingCard } from '@/app/(app)/_components/briefing-card'
import type { DailyBriefing } from '@/lib/coach/briefing-types'

vi.mock('@/app/actions/sessions', () => ({
  applySessionAdjustment: vi.fn(),
}))

afterEach(() => {
  cleanup()
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
