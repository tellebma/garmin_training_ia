// app/(app)/_components/activity-row.tsx
import { Activity as ActivityIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { SPORT_ICON, SPORT_LABEL } from './sport-icon'
import { RouteThumbnail } from './maps/route-thumbnail'
import {
  formatDistanceFromMeters,
  formatDuration,
  formatRelativeDate,
  formatTSS,
} from '@/lib/dashboard/format'
import type { ActivityRowDto, Sport } from '@/lib/dashboard/types'

interface ActivityRowProps {
  activity: ActivityRowDto
  className?: string
}

function knownSport(s: string): s is Sport {
  return (
    s === 'swim' || s === 'bike' || s === 'run' || s === 'brick' || s === 'rest' || s === 'race'
  )
}

export function ActivityRow({ activity, className }: Readonly<ActivityRowProps>) {
  const Icon = knownSport(activity.sport) ? SPORT_ICON[activity.sport] : ActivityIcon
  const label = knownSport(activity.sport) ? SPORT_LABEL[activity.sport] : activity.sport

  return (
    <div
      className={cn(
        'border-border/50 hover:bg-accent/30 flex items-center gap-3 border-b py-3 last:border-b-0',
        className
      )}
    >
      <Icon size={20} className="text-muted-foreground shrink-0" aria-label={label} />
      {activity.route_polyline ? (
        <RouteThumbnail polyline={activity.route_polyline} className="h-8 w-8 shrink-0" />
      ) : null}
      <div className="min-w-0 flex-1">
        <p className="text-foreground truncate text-sm font-medium">{label}</p>
        <p className="text-muted-foreground mt-0.5 text-xs">
          {formatRelativeDate(activity.start_time)}
        </p>
      </div>
      <div className="text-right text-xs">
        <p className="text-foreground font-medium">
          {formatDuration(activity.duration_s)} · {formatDistanceFromMeters(activity.distance_m)}
        </p>
        <p className="text-muted-foreground mt-0.5">{formatTSS(activity.tss)}</p>
      </div>
    </div>
  )
}
