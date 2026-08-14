// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { SessionCard } from '@/app/(app)/_components/session-card'
import type { PlannedSession } from '@/lib/dashboard/types'

vi.mock('@/app/(app)/_components/regenerate-session-button', () => ({
  RegenerateSessionButton: () => <div data-testid="regenerate" />,
}))
// Le rendu détaillé a son propre test (workout-detail.test.tsx) et exige un
// vrai `Workout` : ici on ne vérifie que son branchement.
vi.mock('@/app/(app)/_components/workout-detail', () => ({
  WorkoutDetail: () => <div data-testid="workout-detail" />,
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

  it('surfaces the abandoned-generation state with a retry button (issue #124)', () => {
    const abandoned: PlannedSession = {
      ...runSession,
      workout: null,
      workout_generation_failures: 3,
    }
    render(<SessionCard session={abandoned} showWorkout />)
    expect(screen.getByText(/génération .*a échoué/i)).toBeTruthy()
    expect(screen.getByTestId('regenerate')).toBeTruthy()
    expect(screen.queryByText('Voir la séance détaillée')).toBeNull()
  })

  it('renders a multisport race day without crashing (issue page blanche /plan)', () => {
    const raceDay: PlannedSession = {
      ...runSession,
      id: 's-race',
      sport: 'triathlon',
      session_type: 'race',
      target_duration_s: null,
      target_tss: null,
      phase: 'race',
      workout: null,
    }
    render(<SessionCard session={raceDay} compact showWorkout />)
    expect(screen.getByText('Triathlon — Course')).toBeTruthy()
  })

  it('falls back to a generic icon for a sport the front does not know yet', () => {
    const unknown = {
      ...runSession,
      id: 's-unknown',
      sport: 'kayak',
    } as unknown as PlannedSession
    render(<SessionCard session={unknown} compact />)
    expect(screen.getByText('kayak — Endurance')).toBeTruthy()
  })

  it('shows nothing special while generation is still pending (few failures)', () => {
    const pending: PlannedSession = {
      ...runSession,
      workout: null,
      workout_generation_failures: 1,
    }
    render(<SessionCard session={pending} showWorkout />)
    expect(screen.queryByText(/génération .*a échoué/i)).toBeNull()
    expect(screen.queryByTestId('regenerate')).toBeNull()
  })
})
