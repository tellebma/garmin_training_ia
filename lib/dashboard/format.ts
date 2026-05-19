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
