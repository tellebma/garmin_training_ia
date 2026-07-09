import type { ActivityFeedbackDto, ActivityRowDto, PlannedSession } from './types'

const DAY_MS = 86_400_000

export type CockpitSport = 'swim' | 'bike' | 'run' | 'brick' | 'other'
export type CoachSignalTone = 'positive' | 'neutral' | 'watch'

export interface PerformanceCockpitInput {
  activities: ActivityRowDto[]
  plannedSessions: PlannedSession[]
  feedback: ActivityFeedbackDto[]
  days: 7 | 28 | 90 | 'all'
  reference?: Date
  sport?: CockpitSport | 'all'
}

export interface WeeklyPerformancePoint {
  week: string
  label: string
  plannedDurationMin: number
  actualDurationMin: number
  plannedTss: number
  actualTss: number
}

export interface DisciplinePerformance {
  sport: CockpitSport
  plannedDurationMin: number
  actualDurationMin: number
  plannedSessions: number
  completedSessions: number
  activities: number
}

export interface PerformanceCockpit {
  plannedSessions: number
  completedSessions: number
  missedSessions: number
  extraActivities: number
  adherencePercent: number | null
  plannedDurationMin: number
  actualDurationMin: number
  plannedTss: number
  actualTss: number
  plannedElevationM: number
  actualElevationM: number
  feedbackCount: number
  averageRpe: number | null
  sessionRpeLoad: number
  harderThanExpectedCount: number
  disciplines: DisciplinePerformance[]
  weekly: WeeklyPerformancePoint[]
  coachSignal: {
    tone: CoachSignalTone
    title: string
    summary: string
  }
}

interface Match {
  planned: PlannedSession
  activity: ActivityRowDto | null
}

function round(value: number): number {
  return Math.round(value)
}

function dateKey(value: string): string {
  return value.slice(0, 10)
}

function normalizeSport(value: string): CockpitSport {
  if (value === 'swim' || value === 'bike' || value === 'run' || value === 'brick') return value
  return 'other'
}

function sportsMatch(planned: string, actual: string): boolean {
  if (planned === actual) return true
  return planned === 'brick' && (actual === 'bike' || actual === 'run' || actual === 'brick')
}

function isoWeekStart(date: Date): Date {
  const out = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()))
  const day = (out.getUTCDay() + 6) % 7
  out.setUTCDate(out.getUTCDate() - day)
  return out
}

function isoWeekKey(date: Date): string {
  return isoWeekStart(date).toISOString().slice(0, 10)
}

function weekLabel(start: Date): string {
  return start.toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', timeZone: 'UTC' })
}

function earliestDate(
  activities: ActivityRowDto[],
  plannedSessions: PlannedSession[],
  reference: Date
): Date {
  const candidates = [
    ...activities.map((activity) => new Date(activity.start_time).getTime()),
    ...plannedSessions.map((session) => new Date(`${session.date}T00:00:00Z`).getTime()),
  ]
  return candidates.length > 0 ? new Date(Math.min(...candidates)) : reference
}

function filterBySport<T extends { sport: string }>(items: T[], sport: CockpitSport | 'all'): T[] {
  if (sport === 'all') return items
  return items.filter((item) => normalizeSport(item.sport) === sport)
}

function matchSessions(plannedSessions: PlannedSession[], activities: ActivityRowDto[]): Match[] {
  const usedActivityIds = new Set<string>()

  return plannedSessions.map((planned) => {
    const activity = activities.find(
      (candidate) =>
        !usedActivityIds.has(candidate.id) &&
        dateKey(candidate.start_time) === planned.date &&
        sportsMatch(planned.sport, candidate.sport)
    )
    if (activity) usedActivityIds.add(activity.id)
    return { planned, activity: activity ?? null }
  })
}

function coachSignal(values: {
  plannedSessions: number
  adherencePercent: number | null
  plannedTss: number
  actualTss: number
  averageRpe: number | null
  harderThanExpectedCount: number
  feedbackCount: number
}): PerformanceCockpit['coachSignal'] {
  if (values.plannedSessions === 0) {
    return {
      tone: 'neutral',
      title: 'Historique en construction',
      summary: 'Le plan ne contient pas encore assez de séances sur cette période pour comparer.',
    }
  }
  if (values.averageRpe !== null && values.averageRpe >= 8) {
    return {
      tone: 'watch',
      title: 'Effort ressenti élevé',
      summary:
        'Les séances renseignées sont exigeantes. Protège la récupération avant de progresser.',
    }
  }
  if (values.feedbackCount >= 2 && values.harderThanExpectedCount / values.feedbackCount >= 0.5) {
    return {
      tone: 'watch',
      title: 'Difficulté au-dessus du prévu',
      summary:
        'Plusieurs séances ont été vécues plus durement que prévu. La charge mérite d’être revue.',
    }
  }
  if (values.plannedTss > 0 && values.actualTss > values.plannedTss * 1.2) {
    return {
      tone: 'watch',
      title: 'Charge au-dessus du plan',
      summary:
        'La charge réalisée dépasse sensiblement la cible. Évite de compenser avec plus d’intensité.',
    }
  }
  if ((values.adherencePercent ?? 0) >= 80) {
    return {
      tone: 'positive',
      title: 'Entraînement bien aligné',
      summary:
        'La majorité des séances prévues a été réalisée. La régularité est le signal principal.',
    }
  }
  return {
    tone: 'neutral',
    title: 'Régularité à reconstruire',
    summary:
      'La période est partiellement réalisée. Reprends le fil du plan sans chercher à rattraper.',
  }
}

export function computePerformanceCockpit({
  activities,
  plannedSessions,
  feedback,
  days,
  reference = new Date(),
  sport = 'all',
}: PerformanceCockpitInput): PerformanceCockpit {
  const referenceKey = reference.toISOString().slice(0, 10)
  const start =
    days === 'all'
      ? earliestDate(activities, plannedSessions, reference)
      : new Date(reference.getTime() - (days - 1) * DAY_MS)
  const startKey = start.toISOString().slice(0, 10)
  const relevantActivities = filterBySport(
    activities.filter((activity) => {
      const key = dateKey(activity.start_time)
      return key >= startKey && key <= referenceKey
    }),
    sport
  )
  const relevantPlanned = filterBySport(
    plannedSessions.filter(
      (session) =>
        session.sport !== 'rest' && session.date >= startKey && session.date <= referenceKey
    ),
    sport
  )
  const matches = matchSessions(relevantPlanned, relevantActivities)
  const matchedActivityIds = new Set(
    matches.flatMap((match) => (match.activity ? [match.activity.id] : []))
  )
  const completedSessions = matchedActivityIds.size
  const feedbackByActivity = new Map(feedback.map((item) => [item.activity_id, item]))
  const relevantFeedback = relevantActivities.flatMap((activity) => {
    const item = feedbackByActivity.get(activity.id)
    return item ? [{ item, activity }] : []
  })

  const weekBuckets = new Map<string, WeeklyPerformancePoint>()
  let cursor = isoWeekStart(start)
  const finalWeek = isoWeekStart(reference)
  while (cursor <= finalWeek) {
    const key = isoWeekKey(cursor)
    weekBuckets.set(key, {
      week: key,
      label: weekLabel(cursor),
      plannedDurationMin: 0,
      actualDurationMin: 0,
      plannedTss: 0,
      actualTss: 0,
    })
    cursor = new Date(cursor.getTime() + 7 * DAY_MS)
  }

  for (const session of relevantPlanned) {
    const bucket = weekBuckets.get(isoWeekKey(new Date(`${session.date}T00:00:00Z`)))
    if (!bucket) continue
    bucket.plannedDurationMin += round((session.target_duration_s ?? 0) / 60)
    bucket.plannedTss += round(session.target_tss ?? 0)
  }
  for (const activity of relevantActivities) {
    const bucket = weekBuckets.get(isoWeekKey(new Date(activity.start_time)))
    if (!bucket) continue
    bucket.actualDurationMin += round((activity.duration_s ?? 0) / 60)
    bucket.actualTss += round(activity.tss ?? 0)
  }

  const disciplines = (['swim', 'bike', 'run', 'brick', 'other'] as const)
    .map((discipline): DisciplinePerformance => {
      const disciplinePlanned = relevantPlanned.filter(
        (session) => normalizeSport(session.sport) === discipline
      )
      const disciplineActivities = relevantActivities.filter(
        (activity) => normalizeSport(activity.sport) === discipline
      )
      return {
        sport: discipline,
        plannedDurationMin: round(
          disciplinePlanned.reduce((sum, session) => sum + (session.target_duration_s ?? 0), 0) / 60
        ),
        actualDurationMin: round(
          disciplineActivities.reduce((sum, activity) => sum + (activity.duration_s ?? 0), 0) / 60
        ),
        plannedSessions: disciplinePlanned.length,
        completedSessions: matches.filter(
          (match) => normalizeSport(match.planned.sport) === discipline && match.activity
        ).length,
        activities: disciplineActivities.length,
      }
    })
    .filter((discipline) => discipline.plannedSessions > 0 || discipline.activities > 0)

  const plannedTss = round(
    relevantPlanned.reduce((sum, session) => sum + (session.target_tss ?? 0), 0)
  )
  const actualTss = round(
    relevantActivities.reduce((sum, activity) => sum + (activity.tss ?? 0), 0)
  )
  const averageRpe =
    relevantFeedback.length > 0
      ? relevantFeedback.reduce((sum, entry) => sum + entry.item.rpe, 0) / relevantFeedback.length
      : null
  const harderThanExpectedCount = relevantFeedback.filter(
    (entry) => entry.item.perceived_difficulty === 'harder'
  ).length
  const adherencePercent =
    relevantPlanned.length > 0 ? round((completedSessions / relevantPlanned.length) * 100) : null

  const signal = coachSignal({
    plannedSessions: relevantPlanned.length,
    adherencePercent,
    plannedTss,
    actualTss,
    averageRpe,
    harderThanExpectedCount,
    feedbackCount: relevantFeedback.length,
  })

  return {
    plannedSessions: relevantPlanned.length,
    completedSessions,
    missedSessions: relevantPlanned.length - completedSessions,
    extraActivities: relevantActivities.filter((activity) => !matchedActivityIds.has(activity.id))
      .length,
    adherencePercent,
    plannedDurationMin: round(
      relevantPlanned.reduce((sum, session) => sum + (session.target_duration_s ?? 0), 0) / 60
    ),
    actualDurationMin: round(
      relevantActivities.reduce((sum, activity) => sum + (activity.duration_s ?? 0), 0) / 60
    ),
    plannedTss,
    actualTss,
    plannedElevationM: round(
      relevantPlanned.reduce((sum, session) => sum + (session.target_elevation_gain_m ?? 0), 0)
    ),
    actualElevationM: round(
      relevantActivities.reduce((sum, activity) => sum + (activity.elevation_gain_m ?? 0), 0)
    ),
    feedbackCount: relevantFeedback.length,
    averageRpe,
    sessionRpeLoad: round(
      relevantFeedback.reduce(
        (sum, entry) => sum + ((entry.activity.duration_s ?? 0) / 60) * entry.item.rpe,
        0
      )
    ),
    harderThanExpectedCount,
    disciplines,
    weekly: Array.from(weekBuckets.values()),
    coachSignal: signal,
  }
}
