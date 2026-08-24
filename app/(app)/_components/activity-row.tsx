// app/(app)/_components/activity-row.tsx
import { Activity as ActivityIcon, Flag, Mountain } from 'lucide-react'
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
      {Array.isArray(activity.route_polyline) && activity.route_polyline.length > 0 ? (
        <RouteThumbnail polyline={activity.route_polyline} className="h-8 w-8 shrink-0" />
      ) : null}
      <div className="min-w-0 flex-1">
        <p className="text-foreground flex items-center gap-2 truncate text-sm font-medium">
          {label}
          {activity.race_goal_id ? (
            <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-600 dark:text-amber-400">
              <Flag size={10} aria-hidden />
              Course
            </span>
          ) : null}
        </p>
        <p className="text-muted-foreground mt-0.5 text-xs">
          {formatRelativeDate(activity.start_time)}
        </p>
      </div>
      <div className="text-right text-xs">
        <p className="text-foreground font-medium">
          {formatDuration(activity.duration_s)} · {formatDistanceFromMeters(activity.distance_m)}
        </p>
        <p className="text-muted-foreground mt-0.5 flex items-center justify-end gap-2">
          <span>{formatTSS(activity.tss)}</span>
          {/* Le D+ ne s'affiche que là où il veut dire quelque chose : une nage
              en bassin ou une sortie plate n'ont pas à porter un « 0 m ». */}
          {activity.elevation_gain_m && activity.elevation_gain_m > 0 ? (
            <span className="flex items-center gap-0.5" title="Dénivelé positif">
              <Mountain size={12} aria-hidden />
              {String(Math.round(activity.elevation_gain_m))} m
            </span>
          ) : null}
        </p>
      </div>
    </div>
  )
}
