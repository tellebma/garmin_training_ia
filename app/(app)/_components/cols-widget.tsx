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
  const [expanded, setExpanded] = useState(false)

  if (summaries.length === 0) {
    return null
  }

  const hiddenCount = summaries.length - VISIBLE_COUNT
  const rows = expanded ? summaries : summaries.slice(0, VISIBLE_COUNT)

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between">
        <h3 className="text-muted-foreground text-xs font-semibold uppercase">{title}</h3>
        <span className="text-muted-foreground text-xs tabular-nums">{summaries.length}</span>
      </div>
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
  )
}

export function ColsWidget({ cols, peaks }: Readonly<{ cols: ColSummary[]; peaks: ColSummary[] }>) {
  if (cols.length === 0 && peaks.length === 0) {
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
