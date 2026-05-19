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
  phase: Phase
  week_offset: number
  notes: string | null
}

export interface ActivityRowDto {
  id: string
  garmin_activity_id: string
  start_time: string
  sport: string
  duration_s: number | null
  distance_km: number | null
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
  score: number | null
  total_seconds: number | null
}

export interface HrvDto {
  date: string
  last_night_avg: number | null
  baseline_low: number | null
  baseline_high: number | null
}
