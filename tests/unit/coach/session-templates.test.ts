import { describe, expect, it } from 'vitest'
import { workoutToMarkdown } from '@/lib/coach/session-templates'
import type { Workout } from '@/lib/coach/workout-types'

const baseTarget = { label: 'Z2' as const, rpe: 4 }

const runWorkout: Workout = {
  warmup: {
    duration_s: 600,
    target: { ...baseTarget },
  },
  main: [
    {
      duration_s: 1800,
      target: { ...baseTarget, pace_low_kmh: 12, pace_high_kmh: 15 },
    },
  ],
  cooldown: {
    duration_s: 300,
    target: { ...baseTarget },
  },
  summary_md: 'Endurance de base.',
}

const swimWorkout: Workout = {
  warmup: {
    duration_s: 300,
    target: { ...baseTarget },
  },
  main: [
    {
      duration_s: 1200,
      target: { ...baseTarget, pace_low_kmh: 2, pace_high_kmh: 3 },
    },
  ],
  cooldown: {
    duration_s: 200,
    target: { ...baseTarget },
  },
  summary_md: 'Endurance natation.',
}

describe('session markdown pace units', () => {
  it('renders run targets in min/km, not km/h', () => {
    const md = workoutToMarkdown(runWorkout, 'run', 'endurance')
    expect(md).toContain('/km')
    expect(md).not.toContain('km/h')
  })

  it('renders swim targets in min/100m, not km/h', () => {
    const md = workoutToMarkdown(swimWorkout, 'swim', 'endurance')
    expect(md).toContain('/100m')
    expect(md).not.toContain('km/h')
  })
})
