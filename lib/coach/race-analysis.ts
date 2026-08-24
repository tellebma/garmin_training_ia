/**
 * Vue course (E23) — reconstruction de l'épreuve et débrief déterministe.
 *
 * Tout est calculé, jamais rédigé par un LLM : le débrief porte sur des chiffres
 * qu'on a déjà (temps par segment, FC, transitions, objectif visé, course
 * précédente). Un modèle n'y apporterait qu'un risque d'analyse inventée sur une
 * épreuve que l'athlète a vécue et dont il vérifiera chaque ligne.
 */

export interface RaceLeg {
  readonly order?: number
  readonly discipline: string
  readonly distance_km?: number | null
  readonly elevation_gain_m?: number | null
}

export interface RaceGoalRow {
  readonly id: string
  readonly race_date: string
  readonly name: string | null
  readonly location: string | null
  readonly discipline: string
  readonly legs: RaceLeg[] | null
  readonly total_distance_km: number | null
  readonly total_elevation_gain_m: number | null
  readonly target_time_seconds: number | null
  readonly prep_start_date?: string | null
}

export interface RaceActivityRow {
  readonly id: string
  readonly garmin_activity_id: number
  readonly start_time: string
  readonly sport: string
  readonly duration_s: number | null
  readonly distance_m: number | null
  readonly elevation_gain_m: number | null
  readonly hr_avg: number | null
  readonly pace_avg_s_per_km: number | null
  readonly tss: number | null
}

export interface RaceSegmentRow {
  readonly garmin_activity_id: number
  readonly segment_index: number
  readonly sport: string
  readonly start_time: string | null
  readonly duration_s: number | null
  readonly distance_m: number | null
  readonly elevation_gain_m: number | null
  readonly hr_avg: number | null
  readonly pace_avg_s_per_km: number | null
}

export interface RaceResultsRow {
  readonly official_time_s: number | null
  readonly swim_time_s: number | null
  readonly t1_time_s: number | null
  readonly bike_time_s: number | null
  readonly t2_time_s: number | null
  readonly run_time_s: number | null
  readonly overall_rank: number | null
  readonly overall_finishers: number | null
  readonly category: string | null
  readonly category_rank: number | null
  readonly category_finishers: number | null
  readonly bib_number: string | null
  readonly results_url: string | null
  readonly weather: string | null
  readonly nutrition: string | null
  readonly gear: string | null
  readonly incidents: string | null
  readonly comment: string | null
}

export interface RaceTimelineEntry {
  readonly key: string
  readonly sport: string
  readonly label: string
  readonly isTransition: boolean
  readonly durationS: number
  readonly distanceM: number | null
  readonly elevationGainM: number | null
  readonly hrAvg: number | null
  readonly paceAvgSPerKm: number | null
  /** Part du temps total de l'épreuve, en pourcentage (0-100). */
  readonly sharePct: number
}

export interface RaceElapsed {
  readonly totalS: number
  readonly source: 'official' | 'garmin'
  readonly targetS: number | null
  /** Positif = plus lent que l'objectif. */
  readonly deltaS: number | null
}

export interface RaceDebrief {
  readonly tone: 'positive' | 'watch'
  readonly verdict: string
  readonly strengths: string[]
  readonly improvements: string[]
}

export interface PreparationSummary {
  readonly sessions: number
  readonly durationS: number
  readonly distanceM: number
  readonly weeks: number
}

export interface RaceComparisonLine {
  readonly sport: string
  readonly label: string
  readonly currentS: number
  readonly previousS: number
  /** Négatif = plus rapide que la fois précédente. */
  readonly deltaS: number
}

export const SEGMENT_LABELS: Readonly<Record<string, string>> = {
  swim: 'Natation',
  bike: 'Vélo',
  run: 'Course à pied',
  transition: 'Transition',
  brick: 'Enchaînement',
}

/**
 * Vitesses de croisière amateur, alignées sur `race_day.RACE_SPEED_KMH` côté worker :
 * la répartition attendue du temps de course et le contenu du jour J doivent
 * raconter la même épreuve.
 */
const REFERENCE_SPEED_KMH: Readonly<Record<string, number>> = {
  swim: 3.2,
  bike: 25,
  run: 10,
}

const TRANSITION_SPORTS = new Set(['transition', 't1', 't2'])
/** Au-delà, le trou entre deux activités n'est plus une transition mais une pause. */
const MAX_RECONSTRUCTED_TRANSITION_S = 30 * 60

export function segmentLabel(sport: string, index: number, sports: readonly string[]): string {
  if (!isTransition(sport)) return SEGMENT_LABELS[sport] ?? sport
  // Sur une épreuve à transitions, T1 et T2 se lisent mieux que « Transition ».
  const rank = sports.slice(0, index).filter(isTransition).length + 1
  return `T${String(rank)}`
}

export function isTransition(sport: string): boolean {
  return TRANSITION_SPORTS.has(sport)
}

function positiveDuration(value: number | null | undefined): number {
  return typeof value === 'number' && value > 0 ? Math.round(value) : 0
}

function nullableNumber(value: number | null | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

/**
 * Ligne de temps de l'épreuve.
 *
 * Deux sources possibles, dans cet ordre : la décomposition multisport
 * (`activity_segments`, E22.1) quand Garmin l'a publiée, sinon les activités
 * rattachées elles-mêmes — certaines montres enregistrent une activité par
 * discipline, les transitions se déduisent alors des trous entre elles.
 */
export function buildRaceTimeline({
  activities,
  segments,
}: {
  readonly activities: readonly RaceActivityRow[]
  readonly segments: readonly RaceSegmentRow[]
}): RaceTimelineEntry[] {
  const raw = segments.length > 0 ? fromSegments(segments) : fromActivities(activities)
  const total = raw.reduce((sum, entry) => sum + entry.durationS, 0)
  const sports = raw.map((entry) => entry.sport)
  return raw.map((entry, index) => ({
    ...entry,
    label: segmentLabel(entry.sport, index, sports),
    sharePct: total > 0 ? (entry.durationS / total) * 100 : 0,
  }))
}

type PartialEntry = Omit<RaceTimelineEntry, 'label' | 'sharePct'>

function fromSegments(segments: readonly RaceSegmentRow[]): PartialEntry[] {
  return [...segments]
    .sort((a, b) => a.segment_index - b.segment_index)
    .map((segment) => ({
      key: `${String(segment.garmin_activity_id)}-${String(segment.segment_index)}`,
      sport: segment.sport,
      isTransition: isTransition(segment.sport),
      durationS: positiveDuration(segment.duration_s),
      distanceM: nullableNumber(segment.distance_m),
      elevationGainM: nullableNumber(segment.elevation_gain_m),
      hrAvg: nullableNumber(segment.hr_avg),
      paceAvgSPerKm: nullableNumber(segment.pace_avg_s_per_km),
    }))
    .filter((entry) => entry.durationS > 0)
}

function fromActivities(activities: readonly RaceActivityRow[]): PartialEntry[] {
  const sorted = [...activities].sort(
    (a, b) => new Date(a.start_time).getTime() - new Date(b.start_time).getTime()
  )
  const entries: PartialEntry[] = []
  sorted.forEach((activity, index) => {
    const previous = sorted[index - 1]
    if (previous) {
      const gap = reconstructedTransitionS(previous, activity)
      if (gap > 0) {
        entries.push({
          key: `gap-${activity.id}`,
          sport: 'transition',
          isTransition: true,
          durationS: gap,
          distanceM: null,
          elevationGainM: null,
          hrAvg: null,
          paceAvgSPerKm: null,
        })
      }
    }
    entries.push({
      key: activity.id,
      sport: activity.sport,
      isTransition: isTransition(activity.sport),
      durationS: positiveDuration(activity.duration_s),
      distanceM: nullableNumber(activity.distance_m),
      elevationGainM: nullableNumber(activity.elevation_gain_m),
      hrAvg: nullableNumber(activity.hr_avg),
      paceAvgSPerKm: nullableNumber(activity.pace_avg_s_per_km),
    })
  })
  return entries.filter((entry) => entry.durationS > 0)
}

function reconstructedTransitionS(previous: RaceActivityRow, next: RaceActivityRow): number {
  const previousEnd =
    new Date(previous.start_time).getTime() + positiveDuration(previous.duration_s) * 1000
  const gapS = Math.round((new Date(next.start_time).getTime() - previousEnd) / 1000)
  if (gapS <= 0 || gapS > MAX_RECONSTRUCTED_TRANSITION_S) return 0
  return gapS
}

/**
 * Temps retenu pour l'épreuve. Le chrono officiel prime quand il existe : la montre
 * démarre et s'arrête toujours un peu à côté de la ligne.
 */
export function resolveRaceElapsed({
  timeline,
  race,
  results,
}: {
  readonly timeline: readonly RaceTimelineEntry[]
  readonly race: RaceGoalRow
  readonly results: RaceResultsRow | null
}): RaceElapsed {
  const garminS = timeline.reduce((sum, entry) => sum + entry.durationS, 0)
  const officialS = positiveDuration(results?.official_time_s)
  const totalS = officialS > 0 ? officialS : garminS
  const targetS = nullableNumber(race.target_time_seconds)
  return {
    totalS,
    source: officialS > 0 ? 'official' : 'garmin',
    targetS,
    deltaS: targetS !== null && totalS > 0 ? totalS - targetS : null,
  }
}

/** Répartition du temps attendue par discipline, d'après les distances des `legs`. */
export function expectedSharePct(race: RaceGoalRow): Record<string, number> {
  const legs = (race.legs ?? []).filter((leg) => typeof leg.distance_km === 'number')
  const hours = legs.map((leg) => {
    const speed = REFERENCE_SPEED_KMH[leg.discipline]
    if (!speed) return 0
    return (leg.distance_km ?? 0) / speed
  })
  const total = hours.reduce((sum, h) => sum + h, 0)
  if (total <= 0) return {}
  const shares: Record<string, number> = {}
  legs.forEach((leg, index) => {
    const legHours = hours[index] ?? 0
    shares[leg.discipline] = (shares[leg.discipline] ?? 0) + (legHours / total) * 100
  })
  return shares
}

export function summarizePreparation(
  activities: readonly RaceActivityRow[],
  prepStartDate: string | null | undefined,
  raceDate: string
): PreparationSummary {
  const start = prepStartDate ? new Date(prepStartDate).getTime() : Number.NEGATIVE_INFINITY
  const end = new Date(`${raceDate}T00:00:00Z`).getTime()
  const inWindow = activities.filter((activity) => {
    const time = new Date(activity.start_time).getTime()
    return time >= start && time < end
  })
  const durationS = inWindow.reduce((sum, a) => sum + positiveDuration(a.duration_s), 0)
  const distanceM = inWindow.reduce((sum, a) => sum + (nullableNumber(a.distance_m) ?? 0), 0)
  const weeks =
    prepStartDate && Number.isFinite(start)
      ? Math.max(1, Math.round((end - start) / 604_800_000))
      : 0
  return { sessions: inWindow.length, durationS, distanceM, weeks }
}

/** Temps par discipline (transitions exclues), pour comparer deux épreuves. */
export function timeBySport(timeline: readonly RaceTimelineEntry[]): Record<string, number> {
  const totals: Record<string, number> = {}
  for (const entry of timeline) {
    if (entry.isTransition) continue
    totals[entry.sport] = (totals[entry.sport] ?? 0) + entry.durationS
  }
  return totals
}

export function compareRaces(
  current: readonly RaceTimelineEntry[],
  previous: readonly RaceTimelineEntry[]
): RaceComparisonLine[] {
  const currentBySport = timeBySport(current)
  const previousBySport = timeBySport(previous)
  const lines: RaceComparisonLine[] = []
  for (const [sport, currentS] of Object.entries(currentBySport)) {
    const previousS = previousBySport[sport]
    if (previousS === undefined) continue
    lines.push({
      sport,
      label: SEGMENT_LABELS[sport] ?? sport,
      currentS,
      previousS,
      deltaS: currentS - previousS,
    })
  }
  return lines
}

function formatDelta(seconds: number): string {
  const abs = Math.abs(Math.round(seconds))
  const minutes = Math.floor(abs / 60)
  const rest = abs % 60
  const body =
    minutes > 0 ? `${String(minutes)} min ${String(rest).padStart(2, '0')} s` : `${String(rest)} s`
  return `${seconds >= 0 ? '+' : '-'}${body}`
}

/** Part du temps total passée en transition, en pourcentage. */
export function transitionSharePct(timeline: readonly RaceTimelineEntry[]): number | null {
  const total = timeline.reduce((sum, entry) => sum + entry.durationS, 0)
  if (total <= 0) return null
  const transitions = timeline.filter((entry) => entry.isTransition)
  if (transitions.length === 0) return null
  return (transitions.reduce((sum, entry) => sum + entry.durationS, 0) / total) * 100
}

const SLOW_TRANSITION_PCT = 6
const FAST_TRANSITION_PCT = 3
const PACING_TOLERANCE_PCT = 15

export function buildRaceDebrief({
  race,
  timeline,
  elapsed,
  previousTimeline,
  preparation,
}: {
  readonly race: RaceGoalRow
  readonly timeline: readonly RaceTimelineEntry[]
  readonly elapsed: RaceElapsed
  readonly previousTimeline: readonly RaceTimelineEntry[] | null
  readonly preparation: PreparationSummary | null
}): RaceDebrief {
  const strengths: string[] = []
  const improvements: string[] = []

  appendObjectiveInsight(elapsed, strengths, improvements)
  appendTransitionInsight(timeline, strengths, improvements)
  appendPacingInsight(race, timeline, strengths, improvements)
  appendEffortInsight(timeline, strengths, improvements)
  appendComparisonInsight(timeline, previousTimeline, strengths, improvements)
  appendPreparationInsight(preparation, strengths)

  if (strengths.length === 0) {
    strengths.push('Course terminée : la ligne d’arrivée est déjà un résultat en soi.')
  }
  if (improvements.length === 0) {
    improvements.push(
      'Rien de saillant à corriger sur les données disponibles — complète le ressenti et les résultats officiels pour affiner le débrief.'
    )
  }

  return {
    tone: improvements.length > strengths.length ? 'watch' : 'positive',
    verdict: buildVerdict(elapsed),
    strengths,
    improvements,
  }
}

function buildVerdict(elapsed: RaceElapsed): string {
  if (elapsed.deltaS === null) {
    return 'Course enregistrée. Saisis un temps objectif sur l’épreuve pour situer le résultat.'
  }
  if (elapsed.deltaS <= 0) {
    return `Objectif tenu : ${formatDelta(elapsed.deltaS)} par rapport au temps visé.`
  }
  return `Objectif manqué de ${formatDelta(elapsed.deltaS).replace('+', '')}.`
}

function appendObjectiveInsight(
  elapsed: RaceElapsed,
  strengths: string[],
  improvements: string[]
): void {
  if (elapsed.deltaS === null) return
  if (elapsed.deltaS <= 0) {
    strengths.push(`Temps visé battu de ${formatDelta(elapsed.deltaS).replace('-', '')}.`)
    return
  }
  if (elapsed.targetS !== null && elapsed.deltaS / elapsed.targetS > 0.05) {
    improvements.push(
      `Le temps final dépasse l’objectif de ${formatDelta(elapsed.deltaS).replace('+', '')} : à recaler sur la prochaine épreuve, en visant ou en préparant différemment.`
    )
  }
}

function appendTransitionInsight(
  timeline: readonly RaceTimelineEntry[],
  strengths: string[],
  improvements: string[]
): void {
  const share = transitionSharePct(timeline)
  if (share === null) return
  const transitions = timeline
    .filter((entry) => entry.isTransition)
    .map((entry) => `${entry.label} ${String(Math.round(entry.durationS))} s`)
    .join(', ')
  if (share >= SLOW_TRANSITION_PCT) {
    improvements.push(
      `Les transitions pèsent ${share.toFixed(1)} % du temps total (${transitions}) : c’est du temps gagnable sans aucun gain de forme.`
    )
    return
  }
  if (share <= FAST_TRANSITION_PCT) {
    strengths.push(
      `Transitions propres : ${transitions}, soit ${share.toFixed(1)} % du temps total.`
    )
  }
}

function appendPacingInsight(
  race: RaceGoalRow,
  timeline: readonly RaceTimelineEntry[],
  strengths: string[],
  improvements: string[]
): void {
  const expected = expectedSharePct(race)
  if (Object.keys(expected).length === 0) return
  const actual = timeline.filter((entry) => !entry.isTransition)
  const totalSport = actual.reduce((sum, entry) => sum + entry.durationS, 0)
  if (totalSport <= 0) return

  let aligned = true
  for (const entry of actual) {
    const target = expected[entry.sport]
    if (target === undefined) continue
    const share = (entry.durationS / totalSport) * 100
    const gap = share - target
    if (gap > PACING_TOLERANCE_PCT) {
      aligned = false
      improvements.push(
        `${entry.label} a pris ${share.toFixed(0)} % du temps de course contre ${target.toFixed(0)} % attendus : c’est la partie qui coûte le plus par rapport au format de l’épreuve.`
      )
    } else if (gap < -PACING_TOLERANCE_PCT) {
      strengths.push(
        `${entry.label} tourne à ${share.toFixed(0)} % du temps de course pour ${target.toFixed(0)} % attendus : c’est un point fort du format.`
      )
    }
  }
  if (aligned && actual.length > 1) {
    strengths.push(
      'Répartition du temps conforme au format de l’épreuve, discipline par discipline.'
    )
  }
}

function appendEffortInsight(
  timeline: readonly RaceTimelineEntry[],
  strengths: string[],
  improvements: string[]
): void {
  const withHr = timeline.filter((entry) => !entry.isTransition && entry.hrAvg !== null)
  if (withHr.length < 2) return
  const first = withHr.at(0)
  const last = withHr.at(-1)
  if (!first || !last) return
  const firstHr = first.hrAvg ?? 0
  const lastHr = last.hrAvg ?? 0
  if (lastHr <= firstHr - 5) {
    improvements.push(
      `La FC baisse en fin d’épreuve (${String(firstHr)} bpm sur ${first.label}, ${String(lastHr)} bpm sur ${last.label}) : la dernière discipline s’est courue en gestion, pas à bloc.`
    )
    return
  }
  strengths.push(
    `Intensité tenue jusqu’au bout : ${String(firstHr)} bpm sur ${first.label}, ${String(lastHr)} bpm sur ${last.label}.`
  )
}

function appendComparisonInsight(
  timeline: readonly RaceTimelineEntry[],
  previousTimeline: readonly RaceTimelineEntry[] | null,
  strengths: string[],
  improvements: string[]
): void {
  if (!previousTimeline || previousTimeline.length === 0) return
  for (const line of compareRaces(timeline, previousTimeline)) {
    if (line.deltaS < 0) {
      strengths.push(
        `${line.label} : ${formatDelta(line.deltaS)} par rapport à la course précédente.`
      )
    } else if (line.deltaS > 0) {
      improvements.push(
        `${line.label} : ${formatDelta(line.deltaS)} par rapport à la course précédente.`
      )
    }
  }
}

function appendPreparationInsight(
  preparation: PreparationSummary | null,
  strengths: string[]
): void {
  if (!preparation || preparation.sessions === 0) return
  const hours = Math.round(preparation.durationS / 3600)
  strengths.push(
    `Préparation réellement effectuée : ${String(preparation.sessions)} séances pour ${String(hours)} h d’entraînement.`
  )
}
