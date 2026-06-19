import { SESSION_TYPE_LABEL, SPORT_LABEL } from '../../_components/sport-icon'

export interface CoachAdjustmentDecisionRow {
  id: number
  planned_session_id: string
  original_session_type: string | null
  suggested_session_type: string
  decision: 'accepted' | 'ignored'
  source: string
  created_at: string
  planned_sessions:
    | {
        date: string | null
        sport: string | null
        session_type: string | null
      }
    | {
        date: string | null
        sport: string | null
        session_type: string | null
      }[]
    | null
}

function formatDateTime(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' })
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('fr-FR', { dateStyle: 'medium' })
}

function formatSessionType(sessionType: string | null): string {
  if (!sessionType) return '—'
  const labels: Record<string, string> = SESSION_TYPE_LABEL
  return labels[sessionType] ?? sessionType
}

function formatSport(sport: string | null): string {
  if (!sport) return 'Séance'
  const labels: Record<string, string> = SPORT_LABEL
  return labels[sport] ?? sport
}

function normalizePlannedSession(decision: CoachAdjustmentDecisionRow) {
  const plannedSession = decision.planned_sessions
  if (Array.isArray(plannedSession)) return plannedSession[0] ?? null
  return plannedSession
}

function CoachDecisionStatusBadge({
  decision,
}: Readonly<{ decision: CoachAdjustmentDecisionRow['decision'] }>) {
  const accepted = decision === 'accepted'
  return (
    <span
      className={
        accepted
          ? 'rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-600 dark:text-emerald-400'
          : 'bg-muted text-muted-foreground rounded-full px-3 py-1 text-xs font-medium'
      }
    >
      {accepted ? 'Acceptée' : 'Ignorée'}
    </span>
  )
}

function CoachDecisionItem({ decision }: Readonly<{ decision: CoachAdjustmentDecisionRow }>) {
  const plannedSession = normalizePlannedSession(decision)
  return (
    <li className="space-y-2 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-medium">
            {formatSport(plannedSession?.sport ?? null)} ·{' '}
            {formatDate(plannedSession?.date ?? null)}
          </p>
          <p className="text-muted-foreground text-xs">
            {formatSessionType(decision.original_session_type)} →{' '}
            {formatSessionType(decision.suggested_session_type)}
          </p>
        </div>
        <CoachDecisionStatusBadge decision={decision.decision} />
      </div>
      <p className="text-muted-foreground text-xs">
        Décision enregistrée le {formatDateTime(decision.created_at)}
      </p>
    </li>
  )
}

export function CoachAdjustmentDecisionsSection({
  decisions,
}: Readonly<{ decisions: CoachAdjustmentDecisionRow[] }>) {
  return (
    <section className="space-y-3 rounded-lg border p-6">
      <div>
        <h2 className="text-lg font-semibold">Décisions coach</h2>
        <p className="text-muted-foreground text-sm">
          Historique des adaptations proposées par le coach et de tes choix.
        </p>
      </div>

      {decisions.length === 0 ? (
        <p className="text-muted-foreground text-sm">
          Aucune adaptation acceptée ou ignorée pour le moment.
        </p>
      ) : (
        <ul className="divide-y rounded-lg border">
          {decisions.map((decision) => (
            <CoachDecisionItem key={decision.id} decision={decision} />
          ))}
        </ul>
      )}
    </section>
  )
}
