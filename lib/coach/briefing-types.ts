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
}

export type BriefingResponse =
  | DailyBriefing
  | { status: 'rate_limited'; retry_after_seconds: number }
  | { status: 'unexpected_error'; error_id: string; type: string }

type BriefingErrorResponse = Exclude<BriefingResponse, DailyBriefing>

export function isBriefingError(r: BriefingResponse): r is BriefingErrorResponse {
  return 'status' in r && (r.status === 'rate_limited' || r.status === 'unexpected_error')
}
