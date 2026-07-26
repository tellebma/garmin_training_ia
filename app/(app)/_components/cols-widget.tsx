'use client'

import { useState } from 'react'
import { ChevronDown, Mountain } from 'lucide-react'
import type { ColSummary } from '@/lib/dashboard/cols'
import { cn } from '@/lib/utils'
import { ChartCard } from './chart-card'
import { EmptyState } from './empty-state'

const VISIBLE_COUNT = 10

function crossingsLabel(count: number): string {
  return count === 1 ? '1 fois' : `${String(count)} fois`
}

function ColsTable({ summaries }: Readonly<{ summaries: ColSummary[] }>) {
  return (
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
            <td className="py-2 font-medium">
              {summary.name}
              {summary.type === 'peak' && (
                <span className="text-muted-foreground bg-muted ml-2 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase">
                  sommet
                </span>
              )}
            </td>
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

export function ColsWidget({ summaries }: Readonly<{ summaries: ColSummary[] }>) {
  const [expanded, setExpanded] = useState(false)

  if (summaries.length === 0) {
    return (
      <ChartCard
        title="Mes cols & sommets"
        description="Tes cols et sommets gravis, et ceux à explorer dans un rayon de 50 km"
      >
        <EmptyState
          icon={Mountain}
          title="Aucun col ni sommet recensé"
          description="Aucun col ni sommet dans un rayon de 50 km autour de chez toi."
        />
      </ChartCard>
    )
  }

  const hiddenCount = summaries.length - VISIBLE_COUNT
  const rows = expanded ? summaries : summaries.slice(0, VISIBLE_COUNT)

  return (
    <ChartCard
      title="Mes cols & sommets"
      description="Tes cols et sommets gravis, et ceux à explorer dans un rayon de 50 km"
    >
      <div className="space-y-2">
        <ColsTable summaries={rows} />
        {hiddenCount > 0 && (
          <button
            type="button"
            onClick={() => {
              setExpanded((value) => !value)
            }}
            aria-expanded={expanded}
            className="text-muted-foreground hover:text-foreground flex w-full items-center justify-center gap-1.5 border-t pt-2 text-xs font-medium transition-colors"
          >
            {expanded ? 'Réduire' : `Afficher les ${String(hiddenCount)} autres`}
            <ChevronDown
              className={cn('size-3.5 transition-transform', expanded && 'rotate-180')}
              aria-hidden
            />
          </button>
        )}
      </div>
    </ChartCard>
  )
}
