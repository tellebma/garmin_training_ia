import type { PlannedSession } from '@/lib/dashboard/types'

export type ActivityAnalysisTone = 'positive' | 'watch' | 'risk'

export interface ActivityDetail {
  id: string
  garmin_activity_id: number
  start_time: string
  sport: string
  duration_s: number | null
  distance_m: number | null
  elevation_gain_m: number | null
  tss: number | null
  hr_avg: number | null
  hr_max: number | null
  power_avg: number | null
  power_max: number | null
  pace_avg_s_per_km: number | null
  calories: number | null
}

export interface ActivitySample {
  sample_index: number
  sample_time: string | null
  elapsed_s: number | null
  distance_m: number | null
  elevation_m: number | null
  heart_rate_bpm: number | null
  power_w: number | null
  cadence_rpm: number | null
  speed_m_s: number | null
  latitude: number | null
  longitude: number | null
}

export interface SimilarActivitySummary {
  count: number
  avg_duration_s: number | null
  avg_distance_m: number | null
  avg_elevation_gain_m: number | null
  avg_tss: number | null
  avg_hr_avg: number | null
  avg_power_avg: number | null
}

export interface CoachActivityAnalysis {
  tone: ActivityAnalysisTone
  title: string
  summary: string
  insights: string[]
  recommendations: string[]
  chartData: ActivityComparisonPoint[]
}

export interface ActivityComparisonPoint {
  metric: string
  activity: number | null
  planned: number | null
  similarAvg: number | null
}

export interface HeartRateZoneSummary {
  zone: 'Z1' | 'Z2' | 'Z3' | 'Z4' | 'Z5'
  label: string
  samples: number
  percent: number
}

export interface TerrainSegmentSummary {
  terrain: 'Montée' | 'Plat' | 'Descente'
  distance_m: number
  elevation_delta_m: number
  avg_grade_pct: number | null
  avg_hr_bpm: number | null
  avg_speed_kmh: number | null
  speed_variability_pct: number | null
}

export interface CardioDriftSummary {
  signal: 'stable' | 'watch' | 'risk' | 'insufficient'
  first_half_avg_hr_bpm: number | null
  second_half_avg_hr_bpm: number | null
  drift_bpm: number | null
  drift_pct: number | null
  first_half_avg_speed_kmh: number | null
  second_half_avg_speed_kmh: number | null
  speed_change_pct: number | null
}

export interface SampleCoachSummary {
  hrZones: HeartRateZoneSummary[]
  terrain: TerrainSegmentSummary[]
  cardioDrift: CardioDriftSummary
  insights: string[]
  recommendations: string[]
}

export interface NextSessionAdjustment {
  action: 'maintain' | 'ease' | 'replace_with_recovery' | 'protect_rest'
  title: string
  rationale: string
  recommendation: string
  targetSession: PlannedSession | null
}

interface AnalysisDraft {
  tone: ActivityAnalysisTone
  title: string
  insights: string[]
  recommendations: string[]
}

function ratio(
  actual: number | null | undefined,
  target: number | null | undefined
): number | null {
  if (
    actual === null ||
    actual === undefined ||
    target === null ||
    target === undefined ||
    target <= 0
  ) {
    return null
  }
  return actual / target
}

function round(value: number | null | undefined, digits = 0): number | null {
  if (value === null || value === undefined || Number.isNaN(value)) return null
  const factor = 10 ** digits
  return Math.round(value * factor) / factor
}

function tssPerHour(activity: ActivityDetail): number | null {
  if (!activity.tss || !activity.duration_s || activity.duration_s <= 0) return null
  return activity.tss / (activity.duration_s / 3600)
}

function isEnduranceSport(sport: string): boolean {
  return ['run', 'bike', 'swim', 'brick'].includes(sport)
}

function setWatch(draft: AnalysisDraft): void {
  if (draft.tone !== 'risk') draft.tone = 'watch'
}

function plannedSportMatches(activitySport: string, plannedSport: string): boolean {
  if (activitySport === plannedSport) return true
  if (plannedSport === 'run')
    return ['running', 'trail_running', 'treadmill_running'].includes(activitySport)
  if (plannedSport === 'bike')
    return ['cycling', 'indoor_cycling', 'mountain_biking'].includes(activitySport)
  if (plannedSport === 'swim')
    return ['swimming', 'lap_swimming', 'open_water_swimming'].includes(activitySport)
  return false
}

function applyPlannedContext(
  draft: AnalysisDraft,
  activity: ActivityDetail,
  plannedSession: PlannedSession | null
): void {
  if (!plannedSession) return
  if (plannedSession.session_type === 'rest') {
    draft.tone = 'risk'
    draft.title = 'Activité réalisée sur un jour de repos'
    draft.insights.push(
      'La séance prévue était du repos : cette charge doit compter dans la suite.'
    )
    draft.recommendations.push(
      'Garde la prochaine séance très facile, sans chercher à compenser le plan.'
    )
    return
  }
  if (!plannedSportMatches(activity.sport, plannedSession.sport)) {
    setWatch(draft)
    draft.title = 'Séance différente du plan'
    draft.insights.push(`Le sport réalisé ne correspond pas au ${plannedSession.sport} prévu.`)
    draft.recommendations.push(
      'Ajuste la suite en fonction de la fatigue réelle, pas du plan initial.'
    )
  }
}

function applyExecutionContext(
  draft: AnalysisDraft,
  activity: ActivityDetail,
  plannedSession: PlannedSession | null
): void {
  const durationRatio = ratio(activity.duration_s, plannedSession?.target_duration_s)
  const tssRatio = ratio(activity.tss, plannedSession?.target_tss)
  if (tssRatio !== null && tssRatio >= 1.3) {
    draft.tone = 'risk'
    draft.title = 'Séance plus intense que prévu'
    draft.insights.push('La charge réalisée dépasse nettement la cible du plan.')
    draft.recommendations.push(
      'Évite d’empiler une autre séance dure dans les prochaines 24 à 48 heures.'
    )
    return
  }
  if (durationRatio !== null && durationRatio >= 1.25) {
    setWatch(draft)
    draft.insights.push('La durée réalisée est sensiblement au-dessus de la séance prévue.')
    draft.recommendations.push(
      'Surveille les sensations demain et garde de la marge si les jambes sont lourdes.'
    )
    return
  }
  if (
    durationRatio !== null &&
    durationRatio <= 0.7 &&
    plannedSession?.session_type !== 'recovery'
  ) {
    setWatch(draft)
    draft.title = 'Séance écourtée'
    draft.insights.push('Le volume réalisé est inférieur à l’objectif de la séance.')
    draft.recommendations.push(
      'Ne rattrape pas tout d’un coup : reprends le fil du plan normalement.'
    )
  }
}

function applyElevationContext(
  draft: AnalysisDraft,
  activity: ActivityDetail,
  plannedSession: PlannedSession | null,
  similar: SimilarActivitySummary
): void {
  const elevationRatio = ratio(activity.elevation_gain_m, plannedSession?.target_elevation_gain_m)
  const similarElevationRatio = ratio(activity.elevation_gain_m, similar.avg_elevation_gain_m)
  if (elevationRatio !== null && elevationRatio >= 1.5) {
    setWatch(draft)
    draft.insights.push('Le dénivelé réalisé est nettement supérieur à ce qui était prévu.')
    draft.recommendations.push(
      'Prévois une intensité facile ensuite : le D+ ajoute une vraie fatigue musculaire.'
    )
    return
  }
  if (
    similarElevationRatio !== null &&
    similarElevationRatio >= 1.4 &&
    (activity.elevation_gain_m ?? 0) >= 300
  ) {
    setWatch(draft)
    draft.insights.push('Le dénivelé est élevé par rapport à tes activités similaires récentes.')
  }
}

function applyEffortDensity(draft: AnalysisDraft, activity: ActivityDetail): void {
  const density = tssPerHour(activity)
  if (density === null || density < 75) return
  setWatch(draft)
  draft.insights.push(`Densité élevée : environ ${String(Math.round(density))} TSS/h.`)
  draft.recommendations.push(
    'La prochaine séance doit rester contrôlée, surtout si elle contient du seuil ou des intervalles.'
  )
}

function applyClimbPacing(draft: AnalysisDraft, activity: ActivityDetail): void {
  if (!isEnduranceSport(activity.sport)) return
  if ((activity.elevation_gain_m ?? 0) < 250 || (activity.hr_avg ?? 0) < 155) return
  const targetHr = Math.max(130, (activity.hr_avg ?? 160) - 5)
  draft.recommendations.push(
    `Sur les prochaines montées, laisse baisser l’allure et vise plutôt autour de ${String(targetHr)} bpm.`
  )
}

function applySimilarLoadContext(
  draft: AnalysisDraft,
  activity: ActivityDetail,
  similar: SimilarActivitySummary
): void {
  const similarTssRatio = ratio(activity.tss, similar.avg_tss)
  if (similarTssRatio === null || similarTssRatio < 1.25) return
  setWatch(draft)
  draft.insights.push('Cette activité est plus coûteuse que tes séances similaires récentes.')
}

function fillDefaults(draft: AnalysisDraft): void {
  if (draft.insights.length === 0) {
    draft.insights.push('Exécution cohérente avec la charge attendue et les références récentes.')
  }
  if (draft.recommendations.length === 0) {
    draft.recommendations.push(
      'Continue sur cette régularité, sans ajouter de charge inutile à court terme.'
    )
  }
}

function summaryForTone(tone: ActivityAnalysisTone): string {
  if (tone === 'risk') return 'Activité utile, mais la charge impose de protéger la récupération.'
  if (tone === 'watch')
    return 'Activité intéressante, avec un point de vigilance pour la suite du plan.'
  return 'Activité bien maîtrisée, exploitable pour construire la progression.'
}

function buildChartData(
  activity: ActivityDetail,
  plannedSession: PlannedSession | null,
  similar: SimilarActivitySummary
): ActivityComparisonPoint[] {
  return [
    {
      metric: 'Durée (min)',
      activity: round((activity.duration_s ?? 0) / 60, 1),
      planned: plannedSession?.target_duration_s
        ? round(plannedSession.target_duration_s / 60, 1)
        : null,
      similarAvg: similar.avg_duration_s ? round(similar.avg_duration_s / 60, 1) : null,
    },
    {
      metric: 'Charge TSS',
      activity: round(activity.tss, 1),
      planned: round(plannedSession?.target_tss, 1),
      similarAvg: round(similar.avg_tss, 1),
    },
    {
      metric: 'D+ (m)',
      activity: round(activity.elevation_gain_m),
      planned: round(plannedSession?.target_elevation_gain_m),
      similarAvg: round(similar.avg_elevation_gain_m),
    },
    {
      metric: 'FC moy.',
      activity: round(activity.hr_avg),
      planned: null,
      similarAvg: round(similar.avg_hr_avg),
    },
    {
      metric: 'Puissance moy.',
      activity: round(activity.power_avg),
      planned: null,
      similarAvg: round(similar.avg_power_avg),
    },
  ]
}

function avgNumber(values: number[]): number | null {
  if (values.length === 0) return null
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

function variabilityPct(values: number[]): number | null {
  if (values.length < 2) return null
  const avg = avgNumber(values)
  if (!avg || avg <= 0) return null
  const variance = values.reduce((sum, value) => sum + (value - avg) ** 2, 0) / values.length
  return (Math.sqrt(variance) / avg) * 100
}

function percentChange(next: number | null, prev: number | null): number | null {
  if (next === null || prev === null || prev <= 0) return null
  return ((next - prev) / prev) * 100
}

function hrZone(hr: number, fcMax: number): HeartRateZoneSummary['zone'] {
  const pct = hr / fcMax
  if (pct < 0.6) return 'Z1'
  if (pct < 0.7) return 'Z2'
  if (pct < 0.8) return 'Z3'
  if (pct < 0.9) return 'Z4'
  return 'Z5'
}

function terrainForGrade(gradePct: number): TerrainSegmentSummary['terrain'] {
  if (gradePct >= 3) return 'Montée'
  if (gradePct <= -3) return 'Descente'
  return 'Plat'
}

function emptyTerrain(): Record<TerrainSegmentSummary['terrain'], TerrainSegmentSummary> {
  return {
    Montée: {
      terrain: 'Montée',
      distance_m: 0,
      elevation_delta_m: 0,
      avg_grade_pct: null,
      avg_hr_bpm: null,
      avg_speed_kmh: null,
      speed_variability_pct: null,
    },
    Plat: {
      terrain: 'Plat',
      distance_m: 0,
      elevation_delta_m: 0,
      avg_grade_pct: null,
      avg_hr_bpm: null,
      avg_speed_kmh: null,
      speed_variability_pct: null,
    },
    Descente: {
      terrain: 'Descente',
      distance_m: 0,
      elevation_delta_m: 0,
      avg_grade_pct: null,
      avg_hr_bpm: null,
      avg_speed_kmh: null,
      speed_variability_pct: null,
    },
  }
}

function summarizeHrZones(samples: ActivitySample[], fcMax: number | null): HeartRateZoneSummary[] {
  const usableFcMax = fcMax && fcMax >= 100 ? fcMax : 190
  const zones: HeartRateZoneSummary[] = [
    { zone: 'Z1', label: '<60%', samples: 0, percent: 0 },
    { zone: 'Z2', label: '60-70%', samples: 0, percent: 0 },
    { zone: 'Z3', label: '70-80%', samples: 0, percent: 0 },
    { zone: 'Z4', label: '80-90%', samples: 0, percent: 0 },
    { zone: 'Z5', label: '>90%', samples: 0, percent: 0 },
  ]
  const hrSamples = samples.filter((sample) => typeof sample.heart_rate_bpm === 'number')
  for (const sample of hrSamples) {
    const zone = hrZone(sample.heart_rate_bpm ?? 0, usableFcMax)
    const item = zones.find((z) => z.zone === zone)
    if (item) item.samples += 1
  }
  for (const zone of zones) {
    zone.percent =
      hrSamples.length > 0 ? (round((zone.samples / hrSamples.length) * 100, 1) ?? 0) : 0
  }
  return zones
}

function summarizeTerrain(samples: ActivitySample[]): TerrainSegmentSummary[] {
  const buckets = emptyTerrain()
  const hrValues: Record<TerrainSegmentSummary['terrain'], number[]> = {
    Montée: [],
    Plat: [],
    Descente: [],
  }
  const speedValues: Record<TerrainSegmentSummary['terrain'], number[]> = {
    Montée: [],
    Plat: [],
    Descente: [],
  }

  for (let i = 1; i < samples.length; i += 1) {
    const prev = samples[i - 1]
    const cur = samples[i]
    if (!prev || !cur) continue
    if (
      typeof prev.distance_m !== 'number' ||
      typeof cur.distance_m !== 'number' ||
      typeof prev.elevation_m !== 'number' ||
      typeof cur.elevation_m !== 'number'
    ) {
      continue
    }
    const distanceDelta = cur.distance_m - prev.distance_m
    if (distanceDelta <= 0) continue
    const elevationDelta = cur.elevation_m - prev.elevation_m
    const gradePct = (elevationDelta / distanceDelta) * 100
    const terrain = terrainForGrade(gradePct)
    buckets[terrain].distance_m += distanceDelta
    buckets[terrain].elevation_delta_m += elevationDelta
    if (typeof cur.heart_rate_bpm === 'number') hrValues[terrain].push(cur.heart_rate_bpm)
    if (typeof cur.speed_m_s === 'number') speedValues[terrain].push(cur.speed_m_s * 3.6)
  }

  return (['Montée', 'Plat', 'Descente'] as const).map((terrain) => {
    const bucket = buckets[terrain]
    return {
      ...bucket,
      distance_m: round(bucket.distance_m, 1) ?? 0,
      elevation_delta_m: round(bucket.elevation_delta_m, 1) ?? 0,
      avg_grade_pct:
        bucket.distance_m > 0
          ? round((bucket.elevation_delta_m / bucket.distance_m) * 100, 1)
          : null,
      avg_hr_bpm: round(avgNumber(hrValues[terrain])),
      avg_speed_kmh: round(avgNumber(speedValues[terrain]), 1),
      speed_variability_pct: round(variabilityPct(speedValues[terrain]), 1),
    }
  })
}

function samplePosition(sample: ActivitySample, index: number): number {
  if (typeof sample.elapsed_s === 'number') return sample.elapsed_s
  if (typeof sample.distance_m === 'number') return sample.distance_m
  return index
}

function summarizeCardioDrift(samples: ActivitySample[]): CardioDriftSummary {
  const positioned = samples
    .map((sample, index) => ({ sample, position: samplePosition(sample, index) }))
    .filter(({ sample }) => typeof sample.heart_rate_bpm === 'number')
    .sort((a, b) => a.position - b.position)

  if (positioned.length < 6) {
    return {
      signal: 'insufficient',
      first_half_avg_hr_bpm: null,
      second_half_avg_hr_bpm: null,
      drift_bpm: null,
      drift_pct: null,
      first_half_avg_speed_kmh: null,
      second_half_avg_speed_kmh: null,
      speed_change_pct: null,
    }
  }

  const midpoint = Math.floor(positioned.length / 2)
  const firstHalf = positioned.slice(0, midpoint).map(({ sample }) => sample)
  const secondHalf = positioned.slice(midpoint).map(({ sample }) => sample)
  const firstHr = round(avgNumber(firstHalf.map((sample) => sample.heart_rate_bpm ?? 0)))
  const secondHr = round(avgNumber(secondHalf.map((sample) => sample.heart_rate_bpm ?? 0)))
  const firstSpeed = round(
    avgNumber(
      firstHalf
        .map((sample) => sample.speed_m_s)
        .filter((value): value is number => typeof value === 'number')
        .map((value) => value * 3.6)
    ),
    1
  )
  const secondSpeed = round(
    avgNumber(
      secondHalf
        .map((sample) => sample.speed_m_s)
        .filter((value): value is number => typeof value === 'number')
        .map((value) => value * 3.6)
    ),
    1
  )
  const driftBpm = firstHr !== null && secondHr !== null ? round(secondHr - firstHr) : null
  const driftPct = round(percentChange(secondHr, firstHr), 1)
  const speedChangePct = round(percentChange(secondSpeed, firstSpeed), 1)
  let signal: CardioDriftSummary['signal'] = 'stable'

  if (driftBpm !== null && driftBpm >= 8 && (speedChangePct ?? 0) <= 5) {
    signal = 'risk'
  } else if (driftBpm !== null && driftBpm >= 5 && (speedChangePct ?? 0) <= 8) {
    signal = 'watch'
  }

  return {
    signal,
    first_half_avg_hr_bpm: firstHr,
    second_half_avg_hr_bpm: secondHr,
    drift_bpm: driftBpm,
    drift_pct: driftPct,
    first_half_avg_speed_kmh: firstSpeed,
    second_half_avg_speed_kmh: secondSpeed,
    speed_change_pct: speedChangePct,
  }
}

function sampleInsights(
  zones: HeartRateZoneSummary[],
  terrain: TerrainSegmentSummary[],
  cardioDrift: CardioDriftSummary
): Pick<SampleCoachSummary, 'insights' | 'recommendations'> {
  const insights: string[] = []
  const recommendations: string[] = []
  const highIntensity = zones
    .filter((zone) => zone.zone === 'Z4' || zone.zone === 'Z5')
    .reduce((sum, zone) => sum + zone.percent, 0)
  const climb = terrain.find((item) => item.terrain === 'Montée')
  const irregularTerrain = terrain
    .filter((item) => item.distance_m >= 200 && (item.speed_variability_pct ?? 0) >= 18)
    .sort((a, b) => (b.speed_variability_pct ?? 0) - (a.speed_variability_pct ?? 0))[0]

  if (highIntensity >= 35) {
    insights.push(`Temps cardio élevé : ${highIntensity.toFixed(1)}% des points en Z4/Z5.`)
    recommendations.push(
      'Prévois de la récupération ou de l’endurance facile avant la prochaine séance dure.'
    )
  }
  if (climb && climb.distance_m >= 200 && (climb.avg_hr_bpm ?? 0) >= 160) {
    insights.push(
      `Montées exigeantes : FC moyenne ${String(Math.round(climb.avg_hr_bpm ?? 0))} bpm.`
    )
    recommendations.push(
      'Dans les prochaines montées, ralentis tôt pour éviter de transformer la sortie en séance seuil.'
    )
  }
  if (cardioDrift.signal === 'risk' || cardioDrift.signal === 'watch') {
    insights.push(
      `Dérive cardio : +${String(cardioDrift.drift_bpm ?? 0)} bpm en seconde moitié pour ${String(cardioDrift.speed_change_pct ?? 0)}% de vitesse.`
    )
    recommendations.push(
      'Sur une séance comparable, pars plus bas en intensité et garde une marge cardio jusqu’à mi-parcours.'
    )
  }
  if (irregularTerrain) {
    insights.push(
      `Pacing irrégulier sur ${irregularTerrain.terrain.toLowerCase()} : ${String(irregularTerrain.speed_variability_pct ?? 0)}% de variabilité vitesse.`
    )
    recommendations.push(
      `Travaille la régularité sur ${irregularTerrain.terrain.toLowerCase()} : accélérations plus courtes, relances contrôlées et effort plus lissé.`
    )
  }
  if (insights.length === 0)
    insights.push('Les samples ne montrent pas de dérive majeure à corriger.')
  if (recommendations.length === 0) {
    recommendations.push('Garde cette régularité et surveille surtout les sensations le lendemain.')
  }
  return { insights, recommendations }
}

export function summarizeSimilarActivities(activities: ActivityDetail[]): SimilarActivitySummary {
  function avg(metric: keyof ActivityDetail): number | null {
    const values = activities
      .map((a) => a[metric])
      .filter((v): v is number => typeof v === 'number' && Number.isFinite(v))
    if (values.length === 0) return null
    return values.reduce((sum, v) => sum + v, 0) / values.length
  }

  return {
    count: activities.length,
    avg_duration_s: round(avg('duration_s')),
    avg_distance_m: round(avg('distance_m')),
    avg_elevation_gain_m: round(avg('elevation_gain_m')),
    avg_tss: round(avg('tss'), 1),
    avg_hr_avg: round(avg('hr_avg')),
    avg_power_avg: round(avg('power_avg')),
  }
}

export function buildActivityCoachAnalysis({
  activity,
  plannedSession,
  similar,
}: {
  activity: ActivityDetail
  plannedSession: PlannedSession | null
  similar: SimilarActivitySummary
}): CoachActivityAnalysis {
  const draft: AnalysisDraft = {
    tone: 'positive',
    title: 'Bonne activité',
    insights: [],
    recommendations: [],
  }

  applyPlannedContext(draft, activity, plannedSession)
  applyExecutionContext(draft, activity, plannedSession)
  applyElevationContext(draft, activity, plannedSession, similar)
  applyEffortDensity(draft, activity)
  applyClimbPacing(draft, activity)
  applySimilarLoadContext(draft, activity, similar)
  fillDefaults(draft)

  return {
    tone: draft.tone,
    title: draft.title,
    summary: summaryForTone(draft.tone),
    insights: draft.insights.slice(0, 5),
    recommendations: draft.recommendations.slice(0, 4),
    chartData: buildChartData(activity, plannedSession, similar),
  }
}

export function summarizeActivitySamples(
  samples: ActivitySample[],
  fcMax: number | null = null
): SampleCoachSummary {
  const hrZones = summarizeHrZones(samples, fcMax)
  const terrain = summarizeTerrain(samples)
  const cardioDrift = summarizeCardioDrift(samples)
  const { insights, recommendations } = sampleInsights(hrZones, terrain, cardioDrift)
  return { hrZones, terrain, cardioDrift, insights, recommendations }
}

function hardSession(session: PlannedSession): boolean {
  return ['threshold', 'intervals', 'long', 'race'].includes(session.session_type)
}

function easySession(session: PlannedSession): boolean {
  return session.session_type === 'recovery' || session.session_type === 'endurance'
}

export function buildNextSessionAdjustment(
  summary: SampleCoachSummary | null,
  nextSessions: PlannedSession[]
): NextSessionAdjustment {
  const targetSession = nextSessions.find((session) => session.session_type !== 'rest') ?? null
  if (!summary || nextSessions.length === 0) {
    return {
      action: 'maintain',
      title: 'Suite du plan inchangée',
      rationale:
        'Aucune séance future exploitable ou pas assez de données détaillées sur cette activité.',
      recommendation:
        'Garde le plan tel quel et ajuste seulement selon les sensations du lendemain.',
      targetSession,
    }
  }

  const highIntensity = summary.hrZones
    .filter((zone) => zone.zone === 'Z4' || zone.zone === 'Z5')
    .reduce((sum, zone) => sum + zone.percent, 0)
  const hasCardioDrift =
    summary.cardioDrift.signal === 'risk' || summary.cardioDrift.signal === 'watch'
  const hasIrregularPacing = summary.terrain.some(
    (segment) => segment.distance_m >= 200 && (segment.speed_variability_pct ?? 0) >= 18
  )
  const loadSignals = [highIntensity >= 35, hasCardioDrift, hasIrregularPacing].filter(
    Boolean
  ).length

  if (!targetSession) {
    return {
      action: 'protect_rest',
      title: 'Repos à protéger',
      rationale: 'Les prochaines entrées du plan sont du repos.',
      recommendation:
        'Ne compense pas cette activité : garde le repos prévu pour absorber la charge.',
      targetSession,
    }
  }

  if (loadSignals >= 2 && hardSession(targetSession)) {
    return {
      action: 'replace_with_recovery',
      title: 'Alléger la prochaine séance clé',
      rationale:
        'Cette activité combine plusieurs signaux coûteux : intensité cardio, dérive ou pacing irrégulier.',
      recommendation:
        'Transforme la prochaine séance dure en endurance facile ou récupération active, puis reprends le fil du plan.',
      targetSession,
    }
  }

  if ((hasCardioDrift || highIntensity >= 35) && easySession(targetSession)) {
    return {
      action: 'ease',
      title: 'Garder facile',
      rationale: 'La séance suivante est déjà compatible avec l’absorption de cette charge.',
      recommendation:
        'Conserve-la en aisance respiratoire, sans chercher les zones hautes même si les jambes répondent bien.',
      targetSession,
    }
  }

  if (loadSignals >= 1 && hardSession(targetSession)) {
    return {
      action: 'ease',
      title: 'Réduire l’intention',
      rationale: 'Un signal de coût ressort de cette activité avant une séance exigeante.',
      recommendation:
        'Garde la séance, mais baisse l’objectif d’intensité : moins de répétitions, plus de récupération ou cap cardio strict.',
      targetSession,
    }
  }

  return {
    action: 'maintain',
    title: 'Suite cohérente',
    rationale: 'Les signaux détaillés ne demandent pas de modifier fortement la prochaine séance.',
    recommendation: 'Suis le plan prévu et surveille surtout les sensations au réveil.',
    targetSession,
  }
}
