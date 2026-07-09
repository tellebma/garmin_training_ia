import { formatTargetForSport } from '@/lib/dashboard/format'
import {
  isIntervalSet,
  type IntervalBlock,
  type IntervalSet,
  type IntervalTarget,
  type Workout,
} from '@/lib/coach/workout-types'

export type Sport = 'swim' | 'bike' | 'run' | 'brick' | 'rest'
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

const SPORT_LABEL: Record<Sport, string> = {
  swim: 'Natation',
  bike: 'Vélo',
  run: 'Course',
  brick: 'Enchaînement vélo→CAP',
  rest: 'Repos',
}

const TYPE_LABEL: Record<SessionType, string> = {
  endurance: 'Endurance',
  threshold: 'Seuil',
  intervals: 'Fractionné',
  pma: 'PMA',
  sprint: 'Sprint',
  long: 'Sortie longue',
  recovery: 'Récupération',
  race: 'Course',
  rest: 'Repos',
}

function fmtDuration(s: number): string {
  if (s < 60) return `${String(s)}s`
  const m = Math.round(s / 60)
  if (m < 60) return `${String(m)}min`
  const h = Math.floor(m / 60)
  const rem = m % 60
  return rem === 0 ? `${String(h)}h` : `${String(h)}h${String(rem).padStart(2, '0')}`
}

function fmtTarget(t: IntervalTarget, sport: Sport): string {
  if (t.bpm_low !== undefined && t.bpm_low !== null && t.bpm_high) {
    return `${String(t.bpm_low)}-${String(t.bpm_high)} bpm`
  }
  if (sport === 'bike' && t.watts_low && t.watts_high) {
    return `${String(t.watts_low)}-${String(t.watts_high)} W`
  }
  if ((sport === 'run' || sport === 'swim') && t.pace_low_kmh && t.pace_high_kmh) {
    return formatTargetForSport(sport, {
      pace_low_kmh: t.pace_low_kmh,
      pace_high_kmh: t.pace_high_kmh,
    })
  }
  return t.label
}

function renderBlock(b: IntervalBlock, sport: Sport, indent = ''): string {
  const lines = [`${indent}- ${fmtDuration(b.duration_s)} @ ${fmtTarget(b.target, sport)}`]
  if (b.notes) lines.push(`${indent}  *${b.notes}*`)
  return lines.join('\n')
}

function renderSet(s: IntervalSet, sport: Sport): string {
  const repsLabel = `${String(s.reps)} × `
  const workLine = `- ${repsLabel}${fmtDuration(s.work.duration_s)} @ ${fmtTarget(s.work.target, sport)}`
  const restLine = `  Récup ${fmtDuration(s.rest.duration_s)} @ ${fmtTarget(s.rest.target, sport)}`
  const lines = [workLine, restLine]
  if (s.work.notes) lines.push(`  *${s.work.notes}*`)
  return lines.join('\n')
}

export function workoutToMarkdown(w: Workout, sport: Sport, type: SessionType): string {
  const mainLines = w.main.map((block) =>
    isIntervalSet(block) ? renderSet(block, sport) : renderBlock(block, sport)
  )
  const lines: string[] = [
    `## ${SPORT_LABEL[sport]} — ${TYPE_LABEL[type]}`,
    '',
    '### Échauffement',
    renderBlock(w.warmup, sport),
    '',
    '### Corps de séance',
    ...mainLines,
    '',
    '### Retour calme',
    renderBlock(w.cooldown, sport),
    '',
    `*${w.summary_md}*`,
  ]
  if (w.technical_focus) {
    lines.push('', `> Focus technique : ${w.technical_focus}`)
  }
  return lines.join('\n')
}
