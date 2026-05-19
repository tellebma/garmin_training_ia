// app/(app)/_components/session-card.tsx
import { Clock, Zap } from 'lucide-react'
import { cn } from '@/lib/utils'
import { SportIcon, SPORT_LABEL, SESSION_TYPE_LABEL } from './sport-icon'
import { formatDuration, formatTSS } from '@/lib/dashboard/format'
import type { PlannedSession } from '@/lib/dashboard/types'

interface SessionCardProps {
  session: PlannedSession
  compact?: boolean
  className?: string
}

export function SessionCard({ session, compact = false, className }: Readonly<SessionCardProps>) {
  return (
    <article
      className={cn(
        'bg-card flex items-center gap-3 rounded-lg border p-3',
        compact && 'p-2',
        className
      )}
    >
      <div className="bg-muted flex h-10 w-10 shrink-0 items-center justify-center rounded-full">
        <SportIcon sport={session.sport} size={compact ? 16 : 20} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-foreground truncate text-sm font-medium">
          {SPORT_LABEL[session.sport]} — {SESSION_TYPE_LABEL[session.session_type]}
        </p>
        <div className="text-muted-foreground mt-0.5 flex items-center gap-3 text-xs">
          <span className="flex items-center gap-1">
            <Clock size={12} />
            {formatDuration(session.target_duration_s)}
          </span>
          <span className="flex items-center gap-1">
            <Zap size={12} />
            {formatTSS(session.target_tss)}
          </span>
        </div>
      </div>
    </article>
  )
}
