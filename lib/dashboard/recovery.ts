export type RecoveryTrend = 'improving' | 'stable' | 'declining' | 'no_data'
export type RecoveryConfidence = 'high' | 'medium' | 'low' | 'no_data'
export type RecoveryFreshness = 'fresh' | 'stale' | 'no_data'

export interface RecoveryMetric {
  baseline: number | null
  recent: number | null
  trend: RecoveryTrend
  confidence: RecoveryConfidence
  freshness: RecoveryFreshness
  daysCovered: number
  lastDate: string | null
}

export interface RecoverySleep extends RecoveryMetric {
  durationBaselineS: number | null
  durationRecentS: number | null
  scoreBaseline: number | null
  scoreRecent: number | null
}

export interface RecoveryBaselines {
  computedAt: string | null
  hrv: RecoveryMetric
  restingHr: RecoveryMetric
  sleep: RecoverySleep
  stress: RecoveryMetric
  bodyBattery: RecoveryMetric
}

function metric(raw: Record<string, unknown> | null | undefined): RecoveryMetric {
  const r = raw ?? {}
  return {
    baseline: (r.baseline as number | null | undefined) ?? null,
    recent: (r.recent as number | null | undefined) ?? null,
    trend: (r.trend as RecoveryTrend | undefined) ?? 'no_data',
    confidence: (r.confidence as RecoveryConfidence | undefined) ?? 'no_data',
    freshness: (r.freshness as RecoveryFreshness | undefined) ?? 'no_data',
    daysCovered: (r.days_covered as number | undefined) ?? 0,
    lastDate: (r.last_date as string | null | undefined) ?? null,
  }
}

function sleep(raw: Record<string, unknown> | null | undefined): RecoverySleep {
  const r = raw ?? {}
  return {
    ...metric(raw),
    durationBaselineS: (r.duration_baseline_s as number | null | undefined) ?? null,
    durationRecentS: (r.duration_recent_s as number | null | undefined) ?? null,
    scoreBaseline: (r.score_baseline as number | null | undefined) ?? null,
    scoreRecent: (r.score_recent as number | null | undefined) ?? null,
  }
}

export function mapRecoveryRow(row: unknown): RecoveryBaselines | null {
  if (!row || typeof row !== 'object') return null
  const r = row as Record<string, unknown>
  return {
    computedAt: (r.computed_at as string | null) ?? null,
    hrv: metric(r.hrv as Record<string, unknown> | null),
    restingHr: metric(r.resting_hr as Record<string, unknown> | null),
    sleep: sleep(r.sleep as Record<string, unknown> | null),
    stress: metric(r.stress as Record<string, unknown> | null),
    bodyBattery: metric(r.body_battery as Record<string, unknown> | null),
  }
}
