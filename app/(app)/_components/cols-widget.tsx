import { Mountain } from 'lucide-react'
import type { ColSummary } from '@/lib/dashboard/cols'
import { ChartCard } from './chart-card'
import { EmptyState } from './empty-state'

function crossingsLabel(count: number): string {
  return count === 1 ? '1 fois' : `${String(count)} fois`
}

export function ColsWidget({ summaries }: Readonly<{ summaries: ColSummary[] }>) {
  if (summaries.length === 0) {
    return (
      <ChartCard title="Mes cols" description="Cols dans un rayon de 50 km autour de chez toi">
        <EmptyState
          icon={Mountain}
          title="Aucun col recensé"
          description="Aucun col dans un rayon de 50 km autour de chez toi."
        />
      </ChartCard>
    )
  }

  return (
    <ChartCard title="Mes cols" description="Cols dans un rayon de 50 km autour de chez toi">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-muted-foreground border-b text-left text-xs uppercase">
            <th className="py-2 font-medium">Nom</th>
            <th className="py-2 font-medium">Altitude</th>
            <th className="py-2 font-medium">Distance</th>
            <th className="py-2 text-right font-medium">Grimpé</th>
          </tr>
        </thead>
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
    </ChartCard>
  )
}
