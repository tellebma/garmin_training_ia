export type Sport = 'swim' | 'bike' | 'run' | 'brick' | 'rest' | 'race'

export type SessionType =
  | 'endurance'
  | 'threshold'
  | 'intervals'
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
