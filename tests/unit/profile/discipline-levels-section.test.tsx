// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { DisciplineLevelsSection } from '@/app/(app)/profile/_components/discipline-levels-section'

afterEach(() => {
  cleanup()
})

const disciplines = {
  bike: {
    declared: 3,
    effective: 4,
    adjustment: 1,
    confidence: 'high',
    reason: 'Vélo remonté à 4 : entraînement régulier et soutenu.',
    signals: {
      activities_90d: 22,
      sessions_per_week: 2.4,
      sustained: true,
      tss_share: 0.55,
    },
  },
  run: {
    declared: 4,
    effective: 4,
    adjustment: 0,
    confidence: 'high',
    reason: 'Niveau confirmé.',
    signals: {
      activities_90d: 14,
      sessions_per_week: 1.5,
      sustained: true,
      tss_share: 0.41,
    },
  },
}

describe('DisciplineLevelsSection', () => {
  it('shows the effective level and the reason for an adjusted discipline', () => {
    render(<DisciplineLevelsSection disciplines={disciplines} />)
    expect(screen.getByText(/Vélo remonté à 4/)).toBeTruthy()
    // Both disciplines have effective=4, so we expect two rendered "4" spans
    expect(screen.getAllByText('4')).toHaveLength(2)
  })

  it('renders nothing when there are no disciplines', () => {
    const { container } = render(<DisciplineLevelsSection disciplines={{}} />)
    expect(container.innerHTML).toBe('')
  })
})
