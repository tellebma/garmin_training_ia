// MIROIR du worker : garde ces tables alignées avec
// worker/src/garmin_sync/coach/{training_days,duration_bounds}.py.

export interface Strengths {
  swim: number
  bike: number
  run: number
}
type Level = 'beginner' | 'intermediate' | 'advanced'

export function athleteLevel(s: Strengths): Level {
  const mean = (s.swim + s.bike + s.run) / 3
  if (mean < 2.5) return 'beginner'
  if (mean < 3.75) return 'intermediate'
  return 'advanced'
}

function capVolume(hours: number): number {
  if (hours < 5) return 4
  if (hours < 7) return 5
  return 6
}

const CAP_NIVEAU: Record<Level, number> = { beginner: 4, intermediate: 5, advanced: 6 }
const REPOS_LEVEL: Record<Level, number> = { beginner: 2, intermediate: 1, advanced: 1 }

export function trainingDaysCount(args: {
  nAvailable: number
  hours: number
  strengths: Strengths
}): number {
  const level = athleteLevel(args.strengths)
  const reposMin = REPOS_LEVEL[level]
  return Math.max(
    0,
    Math.min(args.nAvailable, capVolume(args.hours), CAP_NIVEAU[level], 7 - reposMin)
  )
}

// Bornes endurance (minutes) en phase "base", miroir partiel de duration_bounds.py.
const ENDURANCE_BOUNDS_MIN: Record<keyof Strengths, [number, number]> = {
  bike: [90, 180],
  run: [40, 60],
  swim: [45, 60],
}

function fmt(min: number): string {
  const h = Math.floor(min / 60)
  const m = min % 60
  if (h === 0) return `${String(m)}min`
  return m === 0 ? `${String(h)}h` : `${String(h)}h${String(m).padStart(2, '0')}`
}

export interface DisciplinePreview {
  sport: keyof Strengths
  enduranceMinLabel: string
}

export function previewPlan(args: { nAvailable: number; hours: number; strengths: Strengths }) {
  const trainingDays = trainingDaysCount(args)
  const restDays = Math.max(0, args.nAvailable - trainingDays) + (7 - args.nAvailable)
  const disciplines: DisciplinePreview[] = (['swim', 'bike', 'run'] as const).map((sport) => {
    const [lo, hi] = ENDURANCE_BOUNDS_MIN[sport]
    const level = args.strengths[sport]
    // niveau faible -> bas de fourchette ; fort -> haut de fourchette
    const ratio = (level - 1) / 4
    const low = Math.round(lo + (hi - lo) * Math.max(0, ratio - 0.15))
    const high = Math.round(lo + (hi - lo) * Math.min(1, ratio + 0.15))
    return { sport, enduranceMinLabel: `${fmt(low)}–${fmt(high)}` }
  })
  return { trainingDays, restDays, disciplines }
}
