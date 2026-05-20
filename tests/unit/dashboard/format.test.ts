import { describe, expect, it } from 'vitest'
import {
  formatTSS,
  formatDuration,
  formatDistanceKm,
  formatRelativeDate,
  formatWeekday,
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
