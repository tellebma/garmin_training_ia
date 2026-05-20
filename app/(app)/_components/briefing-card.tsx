import { cn } from '@/lib/utils'
import type { DailyBriefing, ReadinessStatus } from '@/lib/coach/briefing-types'

const STATUS_LABEL: Record<ReadinessStatus, string> = {
  ready: 'En forme',
  caution: 'Vigilance',
  rest_advised: 'Repos conseillé',
}

const STATUS_CLASSES: Record<ReadinessStatus, string> = {
  ready: 'border-emerald-500/30 bg-emerald-500/5',
  caution: 'border-amber-500/30 bg-amber-500/5',
  rest_advised: 'border-red-500/30 bg-red-500/5',
}

const STATUS_BADGE_CLASSES: Record<ReadinessStatus, string> = {
  ready: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  caution: 'bg-amber-500/10 text-amber-700 dark:text-amber-300',
  rest_advised: 'bg-red-500/10 text-red-700 dark:text-red-300',
}

interface Props {
  briefing: DailyBriefing
}

export function BriefingCard({ briefing }: Readonly<Props>) {
  const { readiness_score, status, explanation_md, suggested_session } = briefing
  return (
    <section
      className={cn('rounded-lg border p-4', STATUS_CLASSES[status])}
      aria-label="Briefing du jour"
    >
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-foreground text-sm font-semibold tracking-wide uppercase">
          Briefing du jour
        </h2>
        <span
          className={cn(
            'rounded-full px-2 py-0.5 text-xs font-medium',
            STATUS_BADGE_CLASSES[status]
          )}
        >
          {STATUS_LABEL[status]} · {String(readiness_score)}/100
        </span>
      </div>
      <p className="text-foreground text-sm whitespace-pre-wrap">{explanation_md}</p>
      {suggested_session && (
        <div className="bg-background mt-3 rounded-md border p-3 text-sm">
          <p className="text-foreground font-medium">Adaptation proposée</p>
          <p className="text-muted-foreground mt-1">{suggested_session.note}</p>
          <p className="text-foreground mt-2 text-xs">
            <span className="font-semibold">{suggested_session.sport}</span> ·{' '}
            <span>{suggested_session.session_type}</span>
          </p>
        </div>
      )}
    </section>
  )
}
