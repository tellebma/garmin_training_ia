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

describe('session markdown pace units', () => {
  it('renders run targets in min/km, not km/h', () => {
    const md = workoutToMarkdown(runWorkout, 'run', 'endurance')
    expect(md).toContain('/km')
    expect(md).not.toContain('km/h')
  })
})
