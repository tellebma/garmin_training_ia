import type { RecoveryBaselines, RecoveryMetric } from '@/lib/dashboard/recovery'

const METRICS: readonly {
  key: keyof Omit<RecoveryBaselines, 'computedAt'>
  label: string
  unit: string
}[] = [
  { key: 'hrv', label: 'HRV', unit: 'ms' },
  { key: 'restingHr', label: 'FC repos', unit: 'bpm' },
  { key: 'sleep', label: 'Sommeil', unit: '' },
  { key: 'stress', label: 'Stress', unit: '' },
  { key: 'bodyBattery', label: 'Body Battery', unit: '' },
]

function trendLabel(trend: RecoveryMetric['trend']): string {
  if (trend === 'improving') return 'Au-dessus de ta moyenne'
  if (trend === 'declining') return 'En dessous de ta moyenne'
  if (trend === 'stable') return 'Dans ta moyenne'
  return 'Pas assez de données'
}

function trendGlyph(trend: RecoveryMetric['trend']): { glyph: string; cls: string } {
  if (trend === 'improving') return { glyph: '↑', cls: 'text-green-500' }
  if (trend === 'declining') return { glyph: '↓', cls: 'text-red-500' }
  if (trend === 'stable') return { glyph: '→', cls: 'text-muted-foreground' }
  return { glyph: '—', cls: 'text-muted-foreground' }
}

function badge(metric: RecoveryMetric): string | null {
  if (metric.confidence === 'low' || metric.confidence === 'no_data') {
    return 'Données insuffisantes'
  }
  if (metric.freshness === 'stale') return 'Donnée ancienne'
  return null
}

function MetricCard({
  label,
  metric,
}: {
  readonly label: string
  readonly metric: RecoveryMetric
}) {
  const { glyph, cls } = trendGlyph(metric.trend)
  const note = badge(metric)
  return (
    <div className="rounded-lg border p-4">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">{label}</span>
        <span className={`text-lg ${cls}`} aria-hidden>
          {glyph}
        </span>
      </div>
      <p className="text-muted-foreground mt-1 text-sm">{trendLabel(metric.trend)}</p>
      {note ? <p className="text-muted-foreground mt-2 text-xs">{note}</p> : null}
    </div>
  )
}

export function RecoveryPanel({ data }: { readonly data: RecoveryBaselines | null }) {
  if (!data) {
    return (
      <div className="rounded-lg border p-6 text-center">
        <p className="text-muted-foreground text-sm">Récupération : bientôt disponible</p>
      </div>
    )
  }
  return (
    <section
      aria-label="Récupération"
      className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
    >
      {METRICS.map(({ key, label }) => (
        <MetricCard key={key} label={label} metric={data[key]} />
      ))}
    </section>
  )
}
