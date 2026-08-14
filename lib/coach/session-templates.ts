// Formatage des séances : convertit un `Workout` (JSONB produit par le worker) en
// libellés lisibles. Le rendu lui-même est du JSX (`WorkoutDetail`) — il n'y a plus
// d'aller-retour par du markdown, qui perdait des informations en chemin (issue #187).
import { formatDistanceFromMeters, formatTargetForSport } from '@/lib/dashboard/format'
import type { IntervalBlock, IntervalSet, IntervalTarget } from '@/lib/coach/workout-types'

export type Sport = 'swim' | 'bike' | 'run' | 'brick' | 'rest'
export type SessionType =
  | 'endurance'
  | 'threshold'
  | 'intervals'
  | 'pma'
  | 'sprint'
  | 'strides'
  | 'long'
  | 'recovery'
  | 'race'
  | 'rest'

export function fmtDuration(s: number): string {
  if (s < 60) return `${String(s)}s`
  const m = Math.round(s / 60)
  if (m < 60) return `${String(m)}min`
  const h = Math.floor(m / 60)
  const rem = m % 60
  return rem === 0 ? `${String(h)}h` : `${String(h)}h${String(rem).padStart(2, '0')}`
}

// 103 s -> "1'43" (format allure/départ natation).
export function fmtSecondsAsMinSec(s: number): string {
  const m = Math.floor(s / 60)
  const sec = Math.round(s % 60)
  return `${String(m)}'${String(sec).padStart(2, '0')}`
}

// Au bord du bassin on compte en minutes'secondes, pas en « 6min ».
function fmtClock(s: number, sport: Sport): string {
  return sport === 'swim' && s < 3600 ? fmtSecondsAsMinSec(s) : fmtDuration(s)
}

function fmtDistance(meters: number, sport: Sport): string {
  if (sport === 'swim' || meters < 1000) return `${String(meters)} m`
  return formatDistanceFromMeters(meters)
}

export interface BlockQuantity {
  // Grandeur principale : la distance en natation et sur un segment de course,
  // la durée partout ailleurs.
  main: string
  // L'autre grandeur, quand elle est connue — masquer la durée en natation
  // rendait invisible toute incohérence distance/durée (issue #187).
  secondary: string | null
}

export function fmtQuantity(b: IntervalBlock, sport: Sport): BlockQuantity {
  const distance = b.distance_m ? fmtDistance(b.distance_m, sport) : null
  const duration = b.duration_s > 0 ? fmtClock(b.duration_s, sport) : null
  // En natation la distance prime (« 400 m »), ailleurs c'est la durée.
  if (distance && (sport === 'swim' || !duration)) {
    return { main: distance, secondary: duration }
  }
  if (duration) return { main: duration, secondary: distance }
  return { main: '—', secondary: null }
}

export interface BlockTarget {
  // Zone d'intensité — le markdown la perdait dès qu'une valeur chiffrée existait.
  zone: string
  // Valeur chiffrée (bpm, watts, allure) quand le profil permet de la calculer.
  detail: string | null
  rpe: number | null
}

function targetDetail(t: IntervalTarget, sport: Sport): string | null {
  if (sport === 'swim' && t.pace_per_100m_low_s && t.pace_per_100m_high_s) {
    return `${fmtSecondsAsMinSec(t.pace_per_100m_low_s)}–${fmtSecondsAsMinSec(t.pace_per_100m_high_s)} /100m`
  }
  if (t.bpm_low !== undefined && t.bpm_low !== null && t.bpm_high) {
    return `${String(t.bpm_low)}-${String(t.bpm_high)} bpm`
  }
  if (sport === 'bike' && t.watts_low && t.watts_high) {
    return `${String(t.watts_low)}-${String(t.watts_high)} W`
  }
  if ((sport === 'run' || sport === 'swim') && t.pace_low_kmh && t.pace_high_kmh) {
    const formatted = formatTargetForSport(sport, {
      pace_low_kmh: t.pace_low_kmh,
      pace_high_kmh: t.pace_high_kmh,
    })
    return formatted === '—' ? null : formatted
  }
  return null
}

export function fmtTarget(t: IntervalTarget, sport: Sport): BlockTarget {
  return {
    zone: t.label,
    detail: targetDetail(t, sport),
    rpe: Number.isFinite(t.rpe) && t.rpe > 0 ? t.rpe : null,
  }
}

// Natation en séries sur distance : convention bord de bassin « départ toutes les
// X » (temps de nage + récup) plutôt qu'une ligne Récup séparée.
export function fmtDeparture(s: IntervalSet, sport: Sport): string | null {
  if (sport !== 'swim' || !s.work.distance_m) return null
  return `départ ${fmtSecondsAsMinSec(s.work.duration_s + s.rest.duration_s)}`
}

// Un résumé peut tenir sur plusieurs lignes (jour de course : objectif, allure,
// nutrition, transitions) — chaque ligne devient un paragraphe.
export function summaryLines(summary: string | null | undefined): string[] {
  if (!summary) return []
  return summary
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
}
