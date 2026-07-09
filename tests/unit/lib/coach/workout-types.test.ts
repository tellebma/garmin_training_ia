import { describe, expect, it } from 'vitest'
import {
  isIntervalSet,
  totalDurationS,
  type IntervalBlock,
  type IntervalSet,
  type Workout,
} from '@/lib/coach/workout-types'

const z1 = { label: 'Z1', rpe: 2 } as const

const block: IntervalBlock = { duration_s: 600, target: z1, notes: null }

describe('workout-types', () => {
  it('isIntervalSet returns true for sets, false for blocks', () => {
    const set: IntervalSet = { reps: 4, work: block, rest: block }
    expect(isIntervalSet(set)).toBe(true)
    expect(isIntervalSet(block)).toBe(false)
  })

  it('totalDurationS includes warmup + cooldown + simple blocks', () => {
    const w: Workout = {
      warmup: { duration_s: 600, target: z1, notes: null },
      main: [{ duration_s: 1800, target: z1, notes: null }],
      cooldown: { duration_s: 300, target: z1, notes: null },
      summary_md: 'ok',
      technical_focus: null,
    }
    expect(totalDurationS(w)).toBe(600 + 1800 + 300)
  })

  it('totalDurationS multiplies sets by reps', () => {
    const work: IntervalBlock = { duration_s: 300, target: z1, notes: null }
    const rest: IntervalBlock = { duration_s: 120, target: z1, notes: null }
    const w: Workout = {
      warmup: { duration_s: 600, target: z1, notes: null },
      main: [{ reps: 5, work, rest }],
      cooldown: { duration_s: 600, target: z1, notes: null },
      summary_md: 'ok',
      technical_focus: null,
    }
    // 600 + 5*(300+120) + 600 = 600 + 2100 + 600 = 3300
    expect(totalDurationS(w)).toBe(3300)
  })

  it('accepts optional cadence fields on IntervalTarget', () => {
    const target = { label: 'Z2', rpe: 5, cadence_low: 100, cadence_high: 110 } as const
    const b: IntervalBlock = { duration_s: 60, target, notes: null }
    expect(b.target.cadence_low).toBe(100)
    expect(b.target.cadence_high).toBe(110)
  })
})
