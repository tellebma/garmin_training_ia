import { cn } from '@/lib/utils'
import type {
  ActivityInsightSeverity,
  DailyBriefing,
  ReadinessStatus,
} from '@/lib/coach/briefing-types'
import { NextSessionAdjustmentActions } from './next-session-adjustment-actions'

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

const INSIGHT_CLASSES: Record<ActivityInsightSeverity, string> = {
  positive: 'border-emerald-500/30 bg-emerald-500/5',
  watch: 'border-amber-500/30 bg-amber-500/5',
  risk: 'border-red-500/30 bg-red-500/5',
}

interface Props {
  briefing: DailyBriefing
}

export function BriefingCard({ briefing }: Readonly<Props>) {
  const {
    readiness_score,
    status,
    explanation_md,
    suggested_session,
    activity_review,
    last_session_feedback,
    coach_recommendation,
    next_session_adjustment,
  } = briefing
  const insights = activity_review.insights.slice(0, 4)
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
      <div className="bg-background mt-3 rounded-md border p-3 text-sm">
        <p className="text-foreground font-medium">{coach_recommendation.title}</p>
        <p className="text-muted-foreground mt-1">{coach_recommendation.rationale}</p>
        <p className="text-foreground mt-2">{coach_recommendation.instruction}</p>
      </div>
      {last_session_feedback && (
        <div
          className={cn(
            'mt-3 rounded-md border p-3 text-sm',
            INSIGHT_CLASSES[last_session_feedback.severity]
          )}
        >
          <p className="text-foreground font-medium">Retour post-séance</p>
          <p className="text-muted-foreground mt-1">{last_session_feedback.message}</p>
          <p className="text-foreground mt-2 text-xs">
            <span className="font-semibold">{last_session_feedback.sport}</span>
            {last_session_feedback.planned_sport && (
              <>
                {' '}
                · prévu : <span>{last_session_feedback.planned_sport}</span>
              </>
            )}
          </p>
        </div>
      )}
      {next_session_adjustment.status === 'suggested' && (
        <div className="bg-background mt-3 rounded-md border p-3 text-sm">
          <p className="text-foreground font-medium">{next_session_adjustment.title}</p>
          <p className="text-muted-foreground mt-1">{next_session_adjustment.rationale}</p>
          <p className="text-foreground mt-2">{next_session_adjustment.instruction}</p>
          {next_session_adjustment.target_session && (
            <p className="text-muted-foreground mt-2 text-xs">
              Cible :{' '}
              <span className="text-foreground font-semibold">
                {next_session_adjustment.target_session.sport ?? 'séance'}
              </span>{' '}
              · {next_session_adjustment.target_session.session_type ?? 'à ajuster'}
              {next_session_adjustment.suggested_session_type && (
                <> -&gt; {next_session_adjustment.suggested_session_type}</>
              )}
            </p>
          )}
          {next_session_adjustment.target_session?.id &&
            next_session_adjustment.suggested_session_type && (
              <NextSessionAdjustmentActions
                sessionId={next_session_adjustment.target_session.id}
                suggestedSessionType={next_session_adjustment.suggested_session_type}
              />
            )}
        </div>
      )}
      {insights.length > 0 && (
        <div className="mt-4 space-y-2">
          <div className="flex items-center justify-between gap-3">
            <p className="text-foreground text-sm font-medium">Revue des activités</p>
            <p className="text-muted-foreground text-xs">
              {String(activity_review.activities_7d)} activités ·{' '}
              {String(Math.round(activity_review.tss_7d))} TSS ·{' '}
              {String(activity_review.elevation_gain_7d)} m D+
            </p>
          </div>
          <ul className="space-y-2">
            {insights.map((insight) => (
              <li
                key={insight.name}
                className={cn(
                  'rounded-md border px-3 py-2 text-sm',
                  INSIGHT_CLASSES[insight.severity]
                )}
              >
                {insight.message}
              </li>
            ))}
          </ul>
        </div>
      )}
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
