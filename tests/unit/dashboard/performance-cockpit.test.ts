import { describe, expect, it } from 'vitest'
import { computePerformanceCockpit } from '@/lib/dashboard/performance-cockpit'
import type { ActivityFeedbackDto, ActivityRowDto, PlannedSession } from '@/lib/dashboard/types'

const reference = new Date('2026-06-19T12:00:00Z')

function planned(overrides: Partial<PlannedSession>): PlannedSession {
  return {
    id: 'session-1',
    date: '2026-06-18',
    sport: 'run',
    session_type: 'endurance',
    target_duration_s: 3600,
    target_tss: 50,
    target_elevation_gain_m: 200,
    phase: 'base',
    week_offset: 0,
    notes: null,
    ...overrides,
  }
}

function activity(overrides: Partial<ActivityRowDto>): ActivityRowDto {
  return {
    id: 'activity-1',
    garmin_activity_id: 1,
    start_time: '2026-06-18T08:00:00Z',
    sport: 'run',
    duration_s: 3300,
    distance_m: 9000,
    elevation_gain_m: 180,
    tss: 48,
    hr_avg: 150,
    ...overrides,
  }
}

function feedback(overrides: Partial<ActivityFeedbackDto>): ActivityFeedbackDto {
  return {
    activity_id: 'activity-1',
    rpe: 7,
    fatigue: 3,
    soreness: 2,
    pain: 0,
    mood: 4,
    perceived_difficulty: 'as_expected',
    pain_area: null,
    comment: null,
    updated_at: '2026-06-18T10:00:00Z',
    ...overrides,
  }
}

describe('computePerformanceCockpit', () => {
  it('matches a planned session with an activity on the same date and sport', () => {
    const result = computePerformanceCockpit({
      activities: [activity({})],
      plannedSessions: [planned({})],
      feedback: [feedback({})],
      days: 7,
      reference,
    })

    expect(result.completedSessions).toBe(1)
    expect(result.missedSessions).toBe(0)
    expect(result.adherencePercent).toBe(100)
    expect(result.actualDurationMin).toBe(55)
    expect(result.sessionRpeLoad).toBe(385)
    expect(result.coachSignal.tone).toBe('positive')
  })

  it('excludes rest days and future sessions from adherence', () => {
    const result = computePerformanceCockpit({
      activities: [],
      plannedSessions: [
        planned({ id: 'rest', sport: 'rest', session_type: 'rest', target_duration_s: 0 }),
        planned({ id: 'future', date: '2026-06-20' }),
      ],
      feedback: [],
      days: 7,
      reference,
    })

    expect(result.plannedSessions).toBe(0)
    expect(result.adherencePercent).toBeNull()
  })

  it('counts unmatched activities as additions outside the plan', () => {
    const result = computePerformanceCockpit({
      activities: [activity({ id: 'bike-extra', sport: 'bike' })],
      plannedSessions: [planned({})],
      feedback: [],
      days: 7,
      reference,
    })

    expect(result.completedSessions).toBe(0)
    expect(result.extraActivities).toBe(1)
  })

  it('filters the cockpit by discipline', () => {
    const result = computePerformanceCockpit({
      activities: [activity({}), activity({ id: 'bike-1', sport: 'bike' })],
      plannedSessions: [planned({}), planned({ id: 'bike-plan', sport: 'bike' })],
      feedback: [],
      days: 28,
      reference,
      sport: 'bike',
    })

    expect(result.plannedSessions).toBe(1)
    expect(result.actualDurationMin).toBe(55)
    expect(result.disciplines).toHaveLength(1)
    expect(result.disciplines[0]?.sport).toBe('bike')
  })

  it('raises a watch signal when perceived effort is repeatedly high', () => {
    const activities = [
      activity({}),
      activity({ id: 'activity-2', start_time: '2026-06-17T08:00:00Z' }),
    ]
    const result = computePerformanceCockpit({
      activities,
      plannedSessions: [planned({}), planned({ id: 'session-2', date: '2026-06-17' })],
      feedback: [
        feedback({ rpe: 9, perceived_difficulty: 'harder' }),
        feedback({ activity_id: 'activity-2', rpe: 8, perceived_difficulty: 'harder' }),
      ],
      days: 7,
      reference,
    })

    expect(result.averageRpe).toBe(8.5)
    expect(result.coachSignal.tone).toBe('watch')
    expect(result.coachSignal.title).toBe('Effort ressenti élevé')
  })
})
