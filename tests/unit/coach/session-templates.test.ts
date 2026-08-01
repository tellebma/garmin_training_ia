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

describe('swim rendering with distances (issue #125)', () => {
  const swimWithDistances: Workout = {
    warmup: {
      duration_s: 480,
      distance_m: 400,
      target: { label: 'Z1', rpe: 2 },
    },
    main: [
      {
        reps: 8,
        work: {
          duration_s: 95,
          distance_m: 100,
          target: { label: 'Z4', rpe: 8, pace_per_100m_low_s: 94, pace_per_100m_high_s: 99 },
        },
        rest: {
          duration_s: 15,
          target: { label: 'Z1', rpe: 2 },
        },
      },
    ],
    cooldown: {
      duration_s: 240,
      distance_m: 200,
      target: { label: 'Z1', rpe: 2 },
    },
    summary_md: 'Séries au seuil.',
  }

  it('renders block distances in meters instead of raw seconds', () => {
    const md = workoutToMarkdown(swimWithDistances, 'swim', 'threshold')
    expect(md).toContain('400 m')
    expect(md).toContain('200 m')
  })

  it('renders sets as reps x meters with a send-off interval', () => {
    const md = workoutToMarkdown(swimWithDistances, 'swim', 'threshold')
    expect(md).toContain('8 × 100 m')
    // départ = work 95s + rest 15s = 110s -> 1'50
    expect(md).toContain("départ 1'50")
  })

  it('renders pace_per_100m targets as mm ss /100m', () => {
    const md = workoutToMarkdown(swimWithDistances, 'swim', 'threshold')
    expect(md).toContain("1'34")
    expect(md).toContain("1'39")
    expect(md).toContain('/100m')
  })

  it('keeps duration rendering for non-swim sports even with distance present', () => {
    const bike: Workout = {
      warmup: { duration_s: 600, distance_m: 5000, target: { label: 'Z1', rpe: 2 } },
      main: [{ duration_s: 3000, target: { label: 'Z2', rpe: 4 } }],
      cooldown: { duration_s: 600, target: { label: 'Z1', rpe: 2 } },
      summary_md: 'Endurance vélo.',
    }
    const md = workoutToMarkdown(bike, 'bike', 'endurance')
    expect(md).toContain('10min')
    expect(md).not.toContain('5000 m')
  })
})
