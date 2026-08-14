import { describe, expect, it } from 'vitest'
import {
  fmtDeparture,
  fmtDuration,
  fmtQuantity,
  fmtSecondsAsMinSec,
  fmtTarget,
  summaryLines,
} from '@/lib/coach/session-templates'
import type { IntervalBlock, IntervalSet } from '@/lib/coach/workout-types'

const z1 = { label: 'Z1', rpe: 2, bpm_low: 130, bpm_high: 145 } as const

function block(partial: Partial<IntervalBlock> = {}): IntervalBlock {
  return { duration_s: 600, target: { label: 'Z2', rpe: 4 }, ...partial }
}

describe('fmtDuration', () => {
  it('renders seconds, minutes and hours', () => {
    expect(fmtDuration(45)).toBe('45s')
    expect(fmtDuration(600)).toBe('10min')
    expect(fmtDuration(3600)).toBe('1h')
    expect(fmtDuration(9120)).toBe('2h32')
  })
})

describe('fmtSecondsAsMinSec', () => {
  it('renders the pool clock format', () => {
    expect(fmtSecondsAsMinSec(103)).toBe("1'43")
    expect(fmtSecondsAsMinSec(110)).toBe("1'50")
  })
})

describe('fmtQuantity', () => {
  it('puts the distance first in swimming and keeps the duration visible (issue #187)', () => {
    expect(fmtQuantity(block({ duration_s: 480, distance_m: 400 }), 'swim')).toEqual({
      main: '400 m',
      secondary: "8'00",
    })
  })

  it('keeps the duration first for other sports even with a distance', () => {
    expect(fmtQuantity(block({ duration_s: 600, distance_m: 5000 }), 'bike')).toEqual({
      main: '10min',
      secondary: '5.0 km',
    })
  })

  it('renders duration only when no distance is known', () => {
    expect(fmtQuantity(block({ duration_s: 1800 }), 'run')).toEqual({
      main: '30min',
      secondary: null,
    })
  })

  it('falls back on the distance when the block carries no duration', () => {
    expect(fmtQuantity(block({ duration_s: 0, distance_m: 200 }), 'run')).toEqual({
      main: '200 m',
      secondary: null,
    })
  })

  it('renders a dash when nothing is measurable', () => {
    expect(fmtQuantity(block({ duration_s: 0 }), 'run')).toEqual({ main: '—', secondary: null })
  })
})

describe('fmtTarget', () => {
  it('keeps the zone alongside the numeric target', () => {
    expect(fmtTarget(z1, 'run')).toEqual({ zone: 'Z1', detail: '130-145 bpm', rpe: 2 })
  })

  it('renders watts on the bike', () => {
    const t = { label: 'Z4', rpe: 8, watts_low: 210, watts_high: 240 } as const
    expect(fmtTarget(t, 'bike').detail).toBe('210-240 W')
  })

  it('renders swim pace in min/100m', () => {
    const t = { label: 'Z4', rpe: 8, pace_per_100m_low_s: 94, pace_per_100m_high_s: 99 } as const
    expect(fmtTarget(t, 'swim').detail).toBe("1'34–1'39 /100m")
  })

  it('renders run pace in min/km, never in km/h', () => {
    const t = { label: 'Z2', rpe: 4, pace_low_kmh: 12, pace_high_kmh: 15 } as const
    const detail = fmtTarget(t, 'run').detail
    expect(detail).toContain('/km')
    expect(detail).not.toContain('km/h')
  })

  it('falls back to the zone alone when no number can be computed', () => {
    expect(fmtTarget({ label: 'Z2', rpe: 4 }, 'bike')).toEqual({
      zone: 'Z2',
      detail: null,
      rpe: 4,
    })
  })
})

describe('fmtDeparture', () => {
  const swimSet: IntervalSet = {
    reps: 8,
    work: { duration_s: 95, distance_m: 100, target: { label: 'Z4', rpe: 8 } },
    rest: { duration_s: 15, target: { label: 'Z1', rpe: 2 } },
  }

  it('turns work + rest into a pool send-off interval', () => {
    expect(fmtDeparture(swimSet, 'swim')).toBe("départ 1'50")
  })

  it('returns nothing outside swimming or without a distance', () => {
    expect(fmtDeparture(swimSet, 'run')).toBeNull()
    expect(
      fmtDeparture({ ...swimSet, work: { ...swimSet.work, distance_m: null } }, 'swim')
    ).toBeNull()
  })
})

describe('summaryLines', () => {
  it('splits a multi-line race-day summary into paragraphs (PR #174)', () => {
    expect(
      summaryLines('Objectif de temps : 3h52.\nAllure cible : Z3.\n\nTransitions : T1/T2.')
    ).toEqual(['Objectif de temps : 3h52.', 'Allure cible : Z3.', 'Transitions : T1/T2.'])
  })

  it('returns an empty list when there is no summary', () => {
    expect(summaryLines(null)).toEqual([])
    expect(summaryLines('   ')).toEqual([])
  })
})
