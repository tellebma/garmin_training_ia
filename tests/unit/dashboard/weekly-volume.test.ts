import { describe, expect, it } from 'vitest'
import { computeWeeklyVolume } from '@/lib/dashboard/weekly-volume'
import type { ActivityRowDto } from '@/lib/dashboard/types'

function mkActivity(overrides: Partial<ActivityRowDto>): ActivityRowDto {
  return {
    id: crypto.randomUUID(),
    garmin_activity_id: 1,
    start_time: '2026-05-19T08:00:00Z',
    sport: 'bike',
    duration_s: 3600,
    distance_m: 30_000,
    elevation_gain_m: 200,
    tss: 60,
    hr_avg: 140,
    ...overrides,
  }
}

describe('computeWeeklyVolume', () => {
  it('groups durations by ISO week + sport in minutes', () => {
    const activities: ActivityRowDto[] = [
      mkActivity({ start_time: '2026-05-19T08:00:00Z', sport: 'bike', duration_s: 3600 }),
      mkActivity({ start_time: '2026-05-19T18:00:00Z', sport: 'run', duration_s: 1800 }),
      mkActivity({ start_time: '2026-05-20T08:00:00Z', sport: 'swim', duration_s: 2700 }),
    ]
    const out = computeWeeklyVolume(activities, 12, new Date('2026-05-19T12:00:00Z'))
    expect(out).toHaveLength(12)
    const lastWeek = out.at(-1)
    expect(lastWeek?.bike).toBe(60)
    expect(lastWeek?.run).toBe(30)
    expect(lastWeek?.swim).toBe(45)
  })

  it('returns N zero-filled weeks when no activities', () => {
    const out = computeWeeklyVolume([], 6, new Date('2026-05-19T12:00:00Z'))
    expect(out).toHaveLength(6)
    out.forEach((w) => {
      expect(w.swim).toBe(0)
      expect(w.bike).toBe(0)
      expect(w.run).toBe(0)
    })
  })

  it('ignores brick/rest/race sports for the 3 series', () => {
    const activities: ActivityRowDto[] = [
      mkActivity({ start_time: '2026-05-19T08:00:00Z', sport: 'brick', duration_s: 7200 }),
      mkActivity({ start_time: '2026-05-19T18:00:00Z', sport: 'unknown', duration_s: 1800 }),
    ]
    const out = computeWeeklyVolume(activities, 1, new Date('2026-05-19T12:00:00Z'))
    const first = out.at(0)
    expect((first?.swim ?? 0) + (first?.bike ?? 0) + (first?.run ?? 0)).toBe(0)
  })

  it('weeks are sorted chronologically (oldest first)', () => {
    const out = computeWeeklyVolume([], 4, new Date('2026-05-19T12:00:00Z'))
    const labels = out.map((w) => w.week)
    expect([...labels].sort((a, b) => a.localeCompare(b))).toEqual(labels)
  })
})
