import { Activity as ActivityIcon, Moon, RefreshCw, User } from 'lucide-react'
import { cn } from '@/lib/utils'

interface SyncTimingsCardProps {
  lastSleepSyncAt: string | null
  lastActivitiesSyncAt: string | null
  lastProfileSyncAt: string | null
  className?: string
  now?: Date
}

interface Row {
  key: 'activities' | 'sleep' | 'profile'
  label: string
  icon: typeof ActivityIcon
  last: string | null
  next: Date
}

function nextSleepSyncUtc(now: Date): Date {
  const next = new Date(now)
  next.setUTCSeconds(0, 0)
  next.setUTCMinutes(0)
  next.setUTCHours(8)
  if (next <= now) next.setUTCDate(next.getUTCDate() + 1)
  return next
}

function nextActivitiesSyncUtc(now: Date): Date {
  for (const hour of [13, 18]) {
    const candidate = new Date(now)
    candidate.setUTCSeconds(0, 0)
    candidate.setUTCMinutes(0)
    candidate.setUTCHours(hour)
    if (candidate > now) return candidate
  }
  const tomorrow = new Date(now)
  tomorrow.setUTCSeconds(0, 0)
  tomorrow.setUTCMinutes(0)
  tomorrow.setUTCHours(13)
  tomorrow.setUTCDate(tomorrow.getUTCDate() + 1)
  return tomorrow
}

function nextProfileSyncUtc(now: Date): Date {
  // Monday 06:00 UTC. getUTCDay: 0=Sun, 1=Mon, ... 6=Sat
  const next = new Date(now)
  next.setUTCSeconds(0, 0)
  next.setUTCMinutes(0)
  next.setUTCHours(6)
  const day = next.getUTCDay()
  let daysUntilMon: number
  if (day === 1) {
    daysUntilMon = next > now ? 0 : 7
  } else {
    daysUntilMon = (8 - day) % 7 || 7
  }
  next.setUTCDate(next.getUTCDate() + daysUntilMon)
  return next
}

function relativePast(iso: string | null, now: Date): string {
  if (!iso) return 'jamais'
  const d = new Date(iso)
  const diffMin = Math.floor((now.getTime() - d.getTime()) / 60_000)
  if (diffMin < 1) return "à l'instant"
  if (diffMin < 60) return `il y a ${String(diffMin)} min`
  const diffHours = Math.floor(diffMin / 60)
  if (diffHours < 24) return `il y a ${String(diffHours)} h`
  const diffDays = Math.floor(diffHours / 24)
  if (diffDays < 7) return `il y a ${String(diffDays)} j`
  return d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit' })
}

function relativeFuture(d: Date, now: Date): string {
  const diffMin = Math.floor((d.getTime() - now.getTime()) / 60_000)
  if (diffMin <= 0) return 'imminent'
  if (diffMin < 60) return `dans ${String(diffMin)} min`
  const sameDay = d.toDateString() === now.toDateString()
  const hhmm = d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
  if (sameDay) return `à ${hhmm}`
  const tomorrow = new Date(now)
  tomorrow.setDate(tomorrow.getDate() + 1)
  if (d.toDateString() === tomorrow.toDateString()) return `demain ${hhmm}`
  return d.toLocaleDateString('fr-FR', { weekday: 'short', day: '2-digit', month: '2-digit' })
}

export function SyncTimingsCard({
  lastSleepSyncAt,
  lastActivitiesSyncAt,
  lastProfileSyncAt,
  className,
  now,
}: Readonly<SyncTimingsCardProps>) {
  const ref = now ?? new Date()
  const rows: Row[] = [
    {
      key: 'activities',
      label: 'Activités',
      icon: ActivityIcon,
      last: lastActivitiesSyncAt,
      next: nextActivitiesSyncUtc(ref),
    },
    {
      key: 'sleep',
      label: 'Sommeil & HRV',
      icon: Moon,
      last: lastSleepSyncAt,
      next: nextSleepSyncUtc(ref),
    },
    {
      key: 'profile',
      label: 'Profil Garmin',
      icon: User,
      last: lastProfileSyncAt,
      next: nextProfileSyncUtc(ref),
    },
  ]

  return (
    <section className={cn('rounded-lg border px-3 py-2', className)} aria-label="Statut Garmin">
      <div className="text-muted-foreground mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold tracking-wide uppercase">
        <RefreshCw size={11} aria-hidden="true" />
        Synchronisation Garmin
      </div>
      <ul className="space-y-1">
        {rows.map((row) => {
          const Icon = row.icon
          return (
            <li key={row.key} className="flex items-center gap-2 text-xs">
              <Icon size={12} className="text-muted-foreground shrink-0" aria-hidden="true" />
              <span className="text-foreground w-24 shrink-0">{row.label}</span>
              <span className="text-muted-foreground flex-1 truncate">
                {relativePast(row.last, ref)}
              </span>
              <span className="text-muted-foreground/80 shrink-0 text-[11px]">
                → {relativeFuture(row.next, ref)}
              </span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
