export function formatTSS(tss: number | null | undefined): string {
  if (tss === null || tss === undefined) return '—'
  return `${String(Math.round(tss))} TSS`
}

export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds || seconds <= 0) return '—'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h === 0) return `${String(m)}min`
  if (m === 0) return `${String(h)}h`
  return `${String(h)}h${String(m).padStart(2, '0')}`
}

export function formatDistanceKm(km: number | null | undefined): string {
  if (km === null || km === undefined) return '—'
  if (km < 10) return `${km.toFixed(1)} km`
  return `${String(Math.round(km))} km`
}

export function formatDistanceFromMeters(meters: number | null | undefined): string {
  if (meters === null || meters === undefined) return '—'
  return formatDistanceKm(meters / 1000)
}

export function formatRelativeDate(isoDate: string, today = new Date()): string {
  const d = new Date(isoDate)
  const diffMs = today.setHours(0, 0, 0, 0) - new Date(d).setHours(0, 0, 0, 0)
  const diffDays = Math.round(diffMs / 86_400_000)
  if (diffDays === 0) return "Aujourd'hui"
  if (diffDays === 1) return 'Hier'
  if (diffDays < 7) return `Il y a ${String(diffDays)} jours`
  if (diffDays < 30) return `Il y a ${String(Math.floor(diffDays / 7))} sem.`
  return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })
}

const FR_WEEKDAY: Record<number, string> = {
  0: 'Dim',
  1: 'Lun',
  2: 'Mar',
  3: 'Mer',
  4: 'Jeu',
  5: 'Ven',
  6: 'Sam',
}

export function formatWeekday(isoDate: string): string {
  const d = new Date(isoDate)
  return FR_WEEKDAY[d.getDay()] ?? ''
}

import type { Sport } from '@/lib/dashboard/types'

type PaceUnit = 'km/h' | 'min/km' | 'min/100m'

export function paceUnitForSport(sport: Sport): PaceUnit {
  if (sport === 'run') return 'min/km'
  if (sport === 'swim') return 'min/100m'
  return 'km/h'
}

// Minutes décimales depuis un nombre de secondes (par km ou par 100 m).
function decimalMinutes(secondsPerUnit: number): number {
  return secondsPerUnit / 60
}

export function speedToSportValue(sport: Sport, speedMs: number | null): number | null {
  if (speedMs === null || speedMs <= 0) return null
  const unit = paceUnitForSport(sport)
  if (unit === 'km/h') return speedMs * 3.6
  if (unit === 'min/km') return decimalMinutes(1000 / speedMs)
  return decimalMinutes(100 / speedMs) // min/100m
}

// "4:35" depuis 4.5833 minutes décimales.
function formatMinutesAsMmSs(minutes: number): string {
  const totalSeconds = Math.round(minutes * 60)
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return `${String(m)}:${String(s).padStart(2, '0')}`
}

export function formatSpeedForSport(sport: Sport, speedMs: number | null): string {
  const value = speedToSportValue(sport, speedMs)
  if (value === null) return '—'
  const unit = paceUnitForSport(sport)
  if (unit === 'km/h') return `${value.toFixed(1)} km/h`
  if (unit === 'min/km') return `${formatMinutesAsMmSs(value)} /km`
  return `${formatMinutesAsMmSs(value)} /100m`
}

export function formatTargetForSport(
  sport: Sport,
  target: { pace_low_kmh: number | null; pace_high_kmh: number | null }
): string {
  const { pace_low_kmh, pace_high_kmh } = target
  if (pace_low_kmh === null || pace_high_kmh === null || pace_low_kmh <= 0 || pace_high_kmh <= 0) {
    return '—'
  }
  const unit = paceUnitForSport(sport)
  if (unit === 'km/h') {
    return `${pace_low_kmh.toFixed(1)}–${pace_high_kmh.toFixed(1)} km/h`
  }
  // km/h -> m/s -> valeur d'allure ; on affiche du plus rapide au plus lent.
  const lowSpeedMs = pace_low_kmh / 3.6
  const highSpeedMs = pace_high_kmh / 3.6
  const paceA = speedToSportValue(sport, lowSpeedMs)
  const paceB = speedToSportValue(sport, highSpeedMs)
  if (paceA === null || paceB === null) return '—'
  const fast = Math.min(paceA, paceB)
  const slow = Math.max(paceA, paceB)
  const suffix = unit === 'min/km' ? '/km' : '/100m'
  return `${formatMinutesAsMmSs(fast)}–${formatMinutesAsMmSs(slow)} ${suffix}`
}
