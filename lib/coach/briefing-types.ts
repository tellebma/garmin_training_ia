// Types mirror the Python dataclasses in worker/src/garmin_sync/coach/briefing.py.
// Keep in sync when adding factors or statuses.

export type ReadinessStatus = 'ready' | 'caution' | 'rest_advised'

export interface ReadinessFactor {
  name: string
  impact: number // signed: negative = penalty, positive = bonus
  explanation: string
}

export interface SuggestedSession {
  sport: string
  session_type: string
  note: string
}

export type CoachRecommendationAction = 'maintain' | 'ease' | 'rest' | 'caution'

export interface CoachRecommendation {
  action: CoachRecommendationAction
  title: string
  rationale: string
  instruction: string
}

export type PlanAdjustmentAction = 'maintain' | 'ease' | 'replace_with_recovery' | 'protect_rest'

export interface NextSessionAdjustment {
  status: 'none' | 'suggested'
  action: PlanAdjustmentAction
  title: string
  rationale: string
  instruction: string
  target_session: {
    id?: string
    date?: string
    sport?: string
    session_type?: string
    target_duration_s?: number | null
    target_tss?: number | null
    phase?: string
  } | null
  suggested_session_type: string | null
}

export type ActivityInsightSeverity = 'positive' | 'watch' | 'risk'

export interface ActivityInsight {
  name: string
  severity: ActivityInsightSeverity
  message: string
  readiness_impact: number
}

export interface ActivityReview {
  lookback_days: number
  activities_7d: number
  activities_28d: number
  tss_7d: number
  avg_weekly_tss_prev_21d: number
  elevation_gain_7d: number
  avg_weekly_elevation_prev_21d: number
  sport_counts_28d: Record<string, number>
  days_since_last_activity: number | null
  insights: ActivityInsight[]
}

export interface SessionFeedback {
  activity_date: string
  sport: string
  planned_sport: string | null
  planned_session_type: string | null
  verdict: string
  severity: ActivityInsightSeverity
  message: string
  readiness_impact: number
}

export interface DailyBriefing {
  date: string
  readiness_score: number
  status: ReadinessStatus
  explanation_md: string
  factors: ReadinessFactor[]
  planned_session: {
    id?: string
    sport?: string
    session_type?: string
    target_duration_s?: number | null
    target_tss?: number | null
    phase?: string
    workout?: unknown
  } | null
  suggested_session: SuggestedSession | null
  activity_review: ActivityReview
  last_session_feedback: SessionFeedback | null
  coach_recommendation: CoachRecommendation
  next_session_adjustment: NextSessionAdjustment
}

export type BriefingResponse =
  | DailyBriefing
  | { status: 'rate_limited'; retry_after_seconds: number }
  | { status: 'unexpected_error'; error_id: string; type: string }

type BriefingErrorResponse = Exclude<BriefingResponse, DailyBriefing>

export function isBriefingError(r: BriefingResponse): r is BriefingErrorResponse {
  return 'status' in r && (r.status === 'rate_limited' || r.status === 'unexpected_error')
}
