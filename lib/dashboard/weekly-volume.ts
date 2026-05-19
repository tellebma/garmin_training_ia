import type { ActivityRowDto, WeeklyVolumePoint } from './types'

function isoWeekLabel(d: Date): string {
  const target = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))
  const dayNr = (target.getUTCDay() + 6) % 7
  target.setUTCDate(target.getUTCDate() - dayNr + 3)
  const firstThursday = new Date(Date.UTC(target.getUTCFullYear(), 0, 4))
  const diff = (target.getTime() - firstThursday.getTime()) / 86_400_000
  const week = 1 + Math.round((diff - 3 + ((firstThursday.getUTCDay() + 6) % 7)) / 7)
  return `${String(target.getUTCFullYear())}-W${String(week).padStart(2, '0')}`
}

function isoWeekStart(d: Date): Date {
  const out = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))
  const dayNr = (out.getUTCDay() + 6) % 7 // Monday=0
  out.setUTCDate(out.getUTCDate() - dayNr)
  return out
}

export function computeWeeklyVolume(
  activities: ActivityRowDto[],
  weeks: number,
  reference: Date = new Date()
): WeeklyVolumePoint[] {
  const buckets = new Map<string, WeeklyVolumePoint>()
  const startOfCurrent = isoWeekStart(reference)

  for (let i = weeks - 1; i >= 0; i--) {
    const ws = new Date(startOfCurrent)
    ws.setUTCDate(ws.getUTCDate() - i * 7)
    const label = isoWeekLabel(ws)
    buckets.set(label, { week: label, swim: 0, bike: 0, run: 0 })
  }

  for (const a of activities) {
    if (!a.duration_s) continue
    const d = new Date(a.start_time)
    const label = isoWeekLabel(d)
    const bucket = buckets.get(label)
    if (!bucket) continue
    const minutes = Math.round(a.duration_s / 60)
    if (a.sport === 'swim') bucket.swim += minutes
    else if (a.sport === 'bike') bucket.bike += minutes
    else if (a.sport === 'run') bucket.run += minutes
  }

  return Array.from(buckets.values()).sort((a, b) => a.week.localeCompare(b.week))
}
