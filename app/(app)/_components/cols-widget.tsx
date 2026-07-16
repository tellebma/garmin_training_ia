import { Mountain } from 'lucide-react'
import type { ColSummary } from '@/lib/dashboard/cols'
import { ChartCard } from './chart-card'
import { EmptyState } from './empty-state'

const VISIBLE_COUNT = 10

function crossingsLabel(count: number): string {
  return count === 1 ? '1 fois' : `${String(count)} fois`
}

function ColsTable({
  summaries,
  showHeader = true,
}: Readonly<{ summaries: ColSummary[]; showHeader?: boolean }>) {
  return (
    <table className="w-full text-sm">
      {showHeader && (
        <thead>
          <tr className="text-muted-foreground border-b text-left text-xs uppercase">
            <th className="py-2 font-medium">Nom</th>
            <th className="py-2 font-medium">Altitude</th>
            <th className="py-2 font-medium">Distance</th>
            <th className="py-2 text-right font-medium">Grimpé</th>
          </tr>
        </thead>
      )}
      <tbody className="divide-y">
        {summaries.map((summary) => (
          <tr key={summary.id}>
            <td className="py-2 font-medium">{summary.name}</td>
            <td className="text-muted-foreground py-2">
              {summary.elevationM === null ? '—' : `${String(summary.elevationM)} m`}
            </td>
            <td className="text-muted-foreground py-2">{summary.distanceKm} km</td>
            <td
              className={
                summary.crossingsCount > 0
                  ? 'py-2 text-right font-medium'
                  : 'text-muted-foreground py-2 text-right'
              }
            >
              {crossingsLabel(summary.crossingsCount)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function ColsSection({ title, summaries }: Readonly<{ title: string; summaries: ColSummary[] }>) {
  if (summaries.length === 0) {
    return null
  }

  const visible = summaries.slice(0, VISIBLE_COUNT)
  const rest = summaries.slice(VISIBLE_COUNT)

  return (
    <div className="space-y-2">
      <h3 className="text-muted-foreground text-xs font-semibold uppercase">{title}</h3>
      <ColsTable summaries={visible} />
      {rest.length > 0 && (
        <details className="mt-2 text-sm">
          <summary className="text-muted-foreground cursor-pointer">
            Afficher les {rest.length} autres
          </summary>
          <div className="mt-2">
            <ColsTable summaries={rest} showHeader={false} />
          </div>
        </details>
      )}
    </div>
  )
}

export function ColsWidget({ cols, peaks }: Readonly<{ cols: ColSummary[]; peaks: ColSummary[] }>) {
  if (cols.length === 0 && peaks.length === 0) {
    return (
      <ChartCard
        title="Mes cols & sommets"
        description="Cols et sommets dans un rayon de 50 km autour de chez toi"
      >
        <EmptyState
          icon={Mountain}
          title="Aucun col ni sommet recensé"
          description="Aucun col ni sommet dans un rayon de 50 km autour de chez toi."
        />
      </ChartCard>
    )
  }

  return (
    <ChartCard
      title="Mes cols & sommets"
      description="Cols et sommets dans un rayon de 50 km autour de chez toi"
    >
      <div className="space-y-6">
        <ColsSection title="Cols" summaries={cols} />
        <ColsSection title="Sommets" summaries={peaks} />
      </div>
    </ChartCard>
  )
}
