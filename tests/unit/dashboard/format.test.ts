import { describe, expect, it } from 'vitest'
import {
  formatTSS,
  formatDuration,
  formatDistanceKm,
  formatRelativeDate,
  formatWeekday,
  paceUnitForSport,
  speedToSportValue,
  formatSpeedForSport,
  formatTargetForSport,
} from '@/lib/dashboard/format'

describe('formatTSS', () => {
  it('renders rounded TSS with unit', () => {
    expect(formatTSS(62.7)).toBe('63 TSS')
    expect(formatTSS(0)).toBe('0 TSS')
  })
  it('handles null/undefined', () => {
    expect(formatTSS(null)).toBe('—')
    expect(formatTSS(undefined)).toBe('—')
  })
})

describe('formatDuration', () => {
  it('formats hours+minutes', () => {
    expect(formatDuration(3600)).toBe('1h')
    expect(formatDuration(5100)).toBe('1h25')
    expect(formatDuration(600)).toBe('10min')
  })
  it('handles zero/null', () => {
    expect(formatDuration(0)).toBe('—')
    expect(formatDuration(null)).toBe('—')
  })
})

describe('formatDistanceKm', () => {
  it('uses 1 decimal under 10km', () => {
    expect(formatDistanceKm(7.45)).toBe('7.5 km')
  })
  it('rounds to int at 10km+', () => {
    expect(formatDistanceKm(42.195)).toBe('42 km')
  })
  it('handles null', () => {
    expect(formatDistanceKm(null)).toBe('—')
  })
})

describe('formatRelativeDate', () => {
  const today = new Date('2026-05-19T12:00:00Z')
  it('today / yesterday', () => {
    expect(formatRelativeDate('2026-05-19', new Date(today))).toBe("Aujourd'hui")
    expect(formatRelativeDate('2026-05-18', new Date(today))).toBe('Hier')
  })
  it('within a week', () => {
    expect(formatRelativeDate('2026-05-16', new Date(today))).toMatch(/Il y a 3 jours/)
  })
})

describe('formatWeekday', () => {
  it('returns French short weekday', () => {
    // 2026-05-19 is a Tuesday
    expect(formatWeekday('2026-05-19')).toBe('Mar')
  })
})

describe('paceUnitForSport', () => {
  it('maps each discipline to its Strava-like unit', () => {
    expect(paceUnitForSport('bike')).toBe('km/h')
    expect(paceUnitForSport('run')).toBe('min/km')
    expect(paceUnitForSport('swim')).toBe('min/100m')
  })
  it('falls back to km/h for non speed/pace sports', () => {
    expect(paceUnitForSport('brick')).toBe('km/h')
    expect(paceUnitForSport('rest')).toBe('km/h')
  })
})

describe('speedToSportValue', () => {
  it('returns km/h for bike', () => {
    // 10 m/s = 36 km/h
    expect(speedToSportValue('bike', 10)).toBeCloseTo(36, 5)
  })
  it('returns decimal minutes per km for run', () => {
    // 10 m/s => 100 s/km => 1.6667 min/km
    expect(speedToSportValue('run', 10)).toBeCloseTo(100 / 60, 4)
  })
  it('returns decimal minutes per 100m for swim', () => {
    // 2 m/s => 50 s/100m => 0.8333 min/100m
    expect(speedToSportValue('swim', 2)).toBeCloseTo(50 / 60, 4)
  })
  it('returns null for null or non-positive speed', () => {
    expect(speedToSportValue('run', null)).toBeNull()
    expect(speedToSportValue('run', 0)).toBeNull()
  })
})

describe('formatSpeedForSport', () => {
  it('formats bike speed in km/h', () => {
    expect(formatSpeedForSport('bike', 10)).toBe('36.0 km/h')
  })
  it('formats run pace as m:ss /km', () => {
    // 3.5714 m/s => 280 s/km => 4:40 /km
    expect(formatSpeedForSport('run', 1000 / 280)).toBe('4:40 /km')
  })
  it('formats swim pace as m:ss /100m', () => {
    // 100 / 105 m/s => 105 s/100m => 1:45 /100m
    expect(formatSpeedForSport('swim', 100 / 105)).toBe('1:45 /100m')
  })
  it('returns dash when speed is missing', () => {
    expect(formatSpeedForSport('run', null)).toBe('—')
    expect(formatSpeedForSport('bike', 0)).toBe('—')
  })
})

describe('formatTargetForSport', () => {
  it('keeps km/h range for bike', () => {
    expect(formatTargetForSport('bike', { pace_low_kmh: 28, pace_high_kmh: 32 })).toBe(
      '28.0–32.0 km/h'
    )
  })
  it('converts km/h range to min/km for run (slower km/h first)', () => {
    // 12 km/h => 5:00 /km ; 15 km/h => 4:00 /km
    expect(formatTargetForSport('run', { pace_low_kmh: 12, pace_high_kmh: 15 })).toBe(
      '4:00–5:00 /km'
    )
  })
  it('converts km/h range to min/100m for swim', () => {
    // 3 km/h => 0.8333 m/s => 120 s/100m => 2:00 /100m
    expect(formatTargetForSport('swim', { pace_low_kmh: 3, pace_high_kmh: 3 })).toBe(
      '2:00–2:00 /100m'
    )
  })
  it('returns dash when bounds are missing', () => {
    expect(formatTargetForSport('run', { pace_low_kmh: null, pace_high_kmh: null })).toBe('—')
  })
})
