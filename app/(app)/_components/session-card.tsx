// app/(app)/_components/session-card.tsx
import { Clock, Zap } from 'lucide-react'
import { cn } from '@/lib/utils'
import { SportIcon, SPORT_LABEL, SESSION_TYPE_LABEL } from './sport-icon'
import { formatDuration, formatTSS } from '@/lib/dashboard/format'
import { workoutToMarkdown } from '@/lib/coach/session-templates'
import type { Sport as CoachSport } from '@/lib/coach/session-templates'
import type { Workout } from '@/lib/coach/workout-types'
import type { PlannedSession } from '@/lib/dashboard/types'
import { RegenerateSessionButton } from './regenerate-session-button'

interface SessionCardProps {
  session: PlannedSession
  compact?: boolean
  className?: string
  showWorkout?: boolean
}

export function SessionCard({
  session,
  compact = false,
  className,
  showWorkout = false,
}: Readonly<SessionCardProps>) {
  const workout = (session.workout ?? null) as Workout | null
  return (
    <div className={cn('space-y-2', className)}>
      <article
        className={cn('bg-card flex items-center gap-3 rounded-lg border p-3', compact && 'p-2')}
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
      {showWorkout && workout && (
        <div className="space-y-2">
          <details className="text-sm">
            <summary className="cursor-pointer font-medium">Voir la séance détaillée</summary>
            <pre className="mt-2 rounded border p-3 text-xs whitespace-pre-wrap">
              {workoutToMarkdown(workout, session.sport as CoachSport, session.session_type)}
            </pre>
          </details>
          <RegenerateSessionButton sessionId={session.id} />
        </div>
      )}
    </div>
  )
}
