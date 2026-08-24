// Aligné sur le check `planned_sessions_sport_check` (migration
// 20260801130000_planned_sessions_multisport) : le jour de course d'un
// multisport porte la discipline parente ('triathlon'/'duathlon'/'aquathlon').
// 'race' reste toléré pour les sports d'activités Garmin historiques.
export type Sport =
  | 'swim'
  | 'bike'
  | 'run'
  | 'brick'
  | 'rest'
  | 'race'
  | 'triathlon'
  | 'duathlon'
  | 'aquathlon'

export type SessionType =
  | 'endurance'
  | 'threshold'
  | 'intervals'
  | 'pma'
  | 'sprint'
  | 'long'
  | 'recovery'
  | 'race'
  | 'rest'

export type Phase = 'base' | 'build' | 'peak' | 'taper' | 'race'

export interface BanisterPoint {
  date: string
  ctl: number
  atl: number
  tsb: number
}

export interface PlannedSession {
  id: string
  date: string
  sport: Sport
  session_type: SessionType
  target_duration_s: number | null
  target_tss: number | null
  target_elevation_gain_m?: number | null
  phase: Phase
  week_offset: number
  notes: string | null
  workout?: unknown
  workout_generated_at?: string | null
  // Compteur d'échecs de génération LLM ; >= 3 => génération abandonnée (issue #124).
  workout_generation_failures?: number | null
}

export interface ActivityRowDto {
  id: string
  garmin_activity_id: number
  start_time: string
  sport: string
  duration_s: number | null
  distance_m: number | null
  elevation_gain_m: number | null
  tss: number | null
  hr_avg: number | null
  route_polyline?: unknown
  /** Course à laquelle l'activité est rattachée (E23) ; null = activité ordinaire. */
  race_goal_id?: string | null
}

export interface WeeklyVolumePoint {
  week: string // ISO week label e.g. "2026-W15"
  swim: number
  bike: number
  run: number
}

export interface RaceGoal {
  race_date: string
  name: string | null
  discipline: string
}

export interface DailyMetricsDto {
  date: string
  body_battery_high: number | null
  body_battery_low: number | null
  body_battery_current: number | null
  stress_avg: number | null
  resting_hr: number | null
}

export interface SleepDto {
  date: string
  sleep_score: number | null
  sleep_duration_s: number | null
}

export interface HrvDto {
  date: string
  hrv_rmssd: number | null
  hrv_status: string | null
  hrv_weekly_avg: number | null
}

export type PerceivedDifficulty = 'easier' | 'as_expected' | 'harder'

export interface ActivityFeedbackDto {
  activity_id: string
  rpe: number
  fatigue: number | null
  soreness: number | null
  pain: number | null
  mood: number | null
  perceived_difficulty: PerceivedDifficulty | null
  pain_area: string | null
  comment: string | null
  updated_at: string
}
