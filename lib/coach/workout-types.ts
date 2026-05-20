export type Zone = 'Z1' | 'Z2' | 'Z3' | 'Z4' | 'Z5'

export interface IntervalTarget {
  label: Zone
  rpe: number // 1-10
  bpm_low?: number | null
  bpm_high?: number | null
  watts_low?: number | null
  watts_high?: number | null
  pace_low_kmh?: number | null
  pace_high_kmh?: number | null
}

export interface IntervalBlock {
  duration_s: number
  target: IntervalTarget
  notes?: string | null
}

export interface IntervalSet {
  reps: number
  work: IntervalBlock
  rest: IntervalBlock
}

export type MainBlock = IntervalBlock | IntervalSet

export interface Workout {
  warmup: IntervalBlock
  main: MainBlock[]
  cooldown: IntervalBlock
  summary_md: string
  technical_focus?: string | null
}

export function isIntervalSet(b: MainBlock): b is IntervalSet {
  return 'reps' in b
}

export function totalDurationS(w: Workout): number {
  let total = w.warmup.duration_s + w.cooldown.duration_s
  for (const block of w.main) {
    if (isIntervalSet(block)) {
      total += block.reps * (block.work.duration_s + block.rest.duration_s)
    } else {
      total += block.duration_s
    }
  }
  return total
}
