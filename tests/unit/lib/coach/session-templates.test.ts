import { describe, expect, it } from 'vitest'
import { workoutToMarkdown } from '@/lib/coach/session-templates'
import type { Workout } from '@/lib/coach/workout-types'

const z1 = { label: 'Z1', rpe: 2, bpm_low: 130, bpm_high: 145 } as const
const z3 = { label: 'Z3', rpe: 6, bpm_low: 155, bpm_high: 170 } as const

function endurance(durationMin: number): Workout {
  return {
    warmup: { duration_s: 600, target: z1, notes: null },
    main: [{ duration_s: durationMin * 60 - 1200, target: z3, notes: null }],
    cooldown: { duration_s: 600, target: z1, notes: null },
    summary_md: 'Bonne séance endurance.',
    technical_focus: 'Cadence régulière.',
  }
}

describe('workoutToMarkdown', () => {
  it('renders endurance run with bpm targets and summary', () => {
    const md = workoutToMarkdown(endurance(60), 'run', 'endurance')
    expect(md).toContain('### Échauffement')
    expect(md).toContain('### Retour calme')
    expect(md).toContain('130-145 bpm')
    expect(md).toContain('Bonne séance endurance')
  })

  it('renders intervals run with sets', () => {
    const z4 = { label: 'Z4', rpe: 8, bpm_low: 170, bpm_high: 185 } as const
    const work = { duration_s: 240, target: z4, notes: null }
    const rest = { duration_s: 120, target: z1, notes: null }
    const w: Workout = {
      warmup: { duration_s: 600, target: z1, notes: null },
      main: [{ reps: 6, work, rest }],
      cooldown: { duration_s: 600, target: z1, notes: null },
      summary_md: 'Séance VMA.',
      technical_focus: 'Foulée tonique.',
    }
    const md = workoutToMarkdown(w, 'run', 'intervals')
    expect(md).toMatch(/6 [×x] /)
    expect(md).toContain('4min') // 240s = 4min
    expect(md).toContain('2min') // 120s rest = 2min
  })

  it('falls back to Z-label when no bpm available', () => {
    const noTarget = { label: 'Z2', rpe: 4 } as const
    const w: Workout = {
      warmup: { duration_s: 600, target: noTarget, notes: null },
      main: [{ duration_s: 1800, target: noTarget, notes: null }],
      cooldown: { duration_s: 600, target: noTarget, notes: null },
      summary_md: 'ok',
      technical_focus: null,
    }
    const md = workoutToMarkdown(w, 'bike', 'endurance')
    expect(md).toContain('Z2')
    expect(md).not.toContain('bpm')
  })

  it('renders bike threshold session', () => {
    const z4 = { label: 'Z4', rpe: 8, watts_low: 210, watts_high: 240 } as const
    const work = { duration_s: 480, target: z4, notes: null }
    const rest = { duration_s: 180, target: z1, notes: null }
    const w: Workout = {
      warmup: { duration_s: 900, target: z1, notes: null },
      main: [{ reps: 3, work, rest }],
      cooldown: { duration_s: 900, target: z1, notes: null },
      summary_md: 'Seuil vélo.',
      technical_focus: 'Pédalage rond.',
    }
    const md = workoutToMarkdown(w, 'bike', 'threshold')
    expect(md).toContain('210-240 W')
  })
})
