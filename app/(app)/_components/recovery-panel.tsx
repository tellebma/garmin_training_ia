import { formatDuration } from '@/lib/dashboard/format'
import type { RecoveryBaselines, RecoveryMetric, RecoverySleep } from '@/lib/dashboard/recovery'

interface MetricSpec {
  key: keyof Omit<RecoveryBaselines, 'computedAt'>
  label: string
  // Sens de la métrique, miroir de `higher_is_better` côté worker
  // (coach/recovery_baselines.py) : le worker renvoie `improving` quand la FC de
  // repos ou le stress *baissent*, il faut donc l'inverse à l'affichage (issue #180).
  higherIsBetter: boolean
  unit: string
}

const METRICS: readonly MetricSpec[] = [
  { key: 'hrv', label: 'HRV', higherIsBetter: true, unit: 'ms' },
  { key: 'restingHr', label: 'FC repos', higherIsBetter: false, unit: 'bpm' },
  { key: 'sleep', label: 'Sommeil', higherIsBetter: true, unit: '/100' },
  { key: 'stress', label: 'Stress', higherIsBetter: false, unit: '' },
  { key: 'bodyBattery', label: 'Body Battery', higherIsBetter: true, unit: '' },
]

// Direction réelle de la valeur : `improving` ne veut pas dire « plus haut ».
function isAboveBaseline(trend: RecoveryMetric['trend'], higherIsBetter: boolean): boolean {
  return trend === 'improving' ? higherIsBetter : !higherIsBetter
}

function trendLabel(trend: RecoveryMetric['trend'], higherIsBetter: boolean): string {
  if (trend === 'stable') return 'Dans ta moyenne'
  if (trend === 'no_data') return 'Pas assez de données'
  const direction = isAboveBaseline(trend, higherIsBetter)
    ? 'Au-dessus de ta moyenne'
    : 'En dessous de ta moyenne'
  return `${direction} · ${trend === 'improving' ? 'bon signe' : 'à surveiller'}`
}

function trendGlyph(
  trend: RecoveryMetric['trend'],
  higherIsBetter: boolean
): { glyph: string; cls: string } {
  if (trend === 'stable') return { glyph: '→', cls: 'text-muted-foreground' }
  if (trend === 'no_data') return { glyph: '—', cls: 'text-muted-foreground' }
  return {
    glyph: isAboveBaseline(trend, higherIsBetter) ? '↑' : '↓',
    cls: trend === 'improving' ? 'text-green-500' : 'text-red-500',
  }
}

function badge(metric: RecoveryMetric): string | null {
  if (metric.confidence === 'low' || metric.confidence === 'no_data') {
    return 'Données insuffisantes'
  }
  if (metric.freshness === 'stale') return 'Donnée ancienne'
  return null
}

// 23.5 -> « 23,5 » ; 26 -> « 26 ». Une décimale suffit pour toutes ces métriques.
function fmtValue(value: number | null): string | null {
  if (value === null || !Number.isFinite(value)) return null
  const rounded = Math.round(value * 10) / 10
  return (Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1)).replace('.', ',')
}

function isSleep(metric: RecoveryMetric): metric is RecoverySleep {
  return 'durationBaselineS' in metric
}

// Le sommeil expose un indice composite (durée + score) : on montre en plus les
// vraies grandeurs, seules lisibles pour l'athlète.
function sleepDetail(metric: RecoverySleep): string | null {
  const recent = metric.durationRecentS ? formatDuration(metric.durationRecentS) : null
  const baseline = metric.durationBaselineS ? formatDuration(metric.durationBaselineS) : null
  if (!recent && !baseline) return null
  const score = metric.scoreRecent === null ? '' : ` · score ${String(metric.scoreRecent)}`
  return `${recent ?? '—'}${score} (moyenne ${baseline ?? '—'})`
}

function MetricValues({
  metric,
  unit,
}: {
  readonly metric: RecoveryMetric
  readonly unit: string
}) {
  const recent = fmtValue(metric.recent)
  const baseline = fmtValue(metric.baseline)
  if (!recent && !baseline) {
    return <p className="text-muted-foreground mt-1 text-2xl font-semibold">—</p>
  }
  const suffix = unit ? ` ${unit}` : ''
  return (
    <p className="mt-1 text-sm">
      <span className="text-foreground text-2xl font-semibold">{recent ?? '—'}</span>
      <span className="text-muted-foreground">{suffix}</span>
      <span className="text-muted-foreground ml-2">
        vs {baseline ?? '—'}
        {suffix} sur 28 j
      </span>
    </p>
  )
}

function MetricCard({
  label,
  metric,
  higherIsBetter,
  unit,
}: {
  readonly label: string
  readonly metric: RecoveryMetric
  readonly higherIsBetter: boolean
  readonly unit: string
}) {
  const { glyph, cls } = trendGlyph(metric.trend, higherIsBetter)
  const note = badge(metric)
  const detail = isSleep(metric) ? sleepDetail(metric) : null
  return (
    <div className="rounded-lg border p-4">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">{label}</span>
        <span className={`text-lg ${cls}`} aria-hidden>
          {glyph}
        </span>
      </div>
      <MetricValues metric={metric} unit={unit} />
      {detail ? <p className="text-muted-foreground mt-1 text-xs">{detail}</p> : null}
      <p className="text-muted-foreground mt-1 text-sm">
        {trendLabel(metric.trend, higherIsBetter)}
      </p>
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
      {METRICS.map(({ key, label, higherIsBetter, unit }) => (
        <MetricCard
          key={key}
          label={label}
          metric={data[key]}
          higherIsBetter={higherIsBetter}
          unit={unit}
        />
      ))}
    </section>
  )
}
