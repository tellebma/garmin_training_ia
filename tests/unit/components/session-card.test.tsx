// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { SessionCard } from '@/app/(app)/_components/session-card'
import type { PlannedSession } from '@/lib/dashboard/types'

vi.mock('@/app/(app)/_components/regenerate-session-button', () => ({
  RegenerateSessionButton: () => <div data-testid="regenerate" />,
}))
vi.mock('@/lib/coach/session-templates', () => ({
  workoutToMarkdown: () => 'WORKOUT_MARKDOWN',
}))

afterEach(() => {
  cleanup()
})

const restSession: PlannedSession = {
  id: 's-rest',
  date: '2026-06-22',
  sport: 'rest',
  session_type: 'rest',
  target_duration_s: 0,
  target_tss: 0,
  target_elevation_gain_m: 0,
  phase: 'base',
  week_offset: 0,
  notes: null,
  workout: { foo: 'bar' },
}

const runSession: PlannedSession = {
  id: 's-run',
  date: '2026-06-22',
  sport: 'run',
  session_type: 'endurance',
  target_duration_s: 3600,
  target_tss: 60,
  target_elevation_gain_m: 0,
  phase: 'base',
  week_offset: 0,
  notes: null,
  workout: { foo: 'bar' },
}

describe('SessionCard', () => {
  it('renders a sober rest variant without metrics, workout or regenerate button', () => {
    render(<SessionCard session={restSession} compact showWorkout />)
    expect(screen.getByText('Repos')).toBeTruthy()
    expect(screen.getByText('Récupération planifiée')).toBeTruthy()
    // no detailed workout / regenerate on a rest day
    expect(screen.queryByText('Voir la séance détaillée')).toBeNull()
    expect(screen.queryByTestId('regenerate')).toBeNull()
    expect(screen.queryByText('1h00')).toBeNull()
  })

  it('renders a normal session with metrics and detailed workout', () => {
    render(<SessionCard session={runSession} compact showWorkout />)
    expect(screen.getByText('Course — Endurance')).toBeTruthy()
    expect(screen.getByText('Voir la séance détaillée')).toBeTruthy()
    expect(screen.getByTestId('regenerate')).toBeTruthy()
    expect(screen.queryByText('Récupération planifiée')).toBeNull()
  })
})
