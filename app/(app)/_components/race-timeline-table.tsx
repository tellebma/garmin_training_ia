import { cn } from '@/lib/utils'
import { formatDistanceFromMeters, formatSpeedForSport } from '@/lib/dashboard/format'
import { formatRaceClock, type RaceTimelineEntry } from '@/lib/coach/race-analysis'
import type { Sport } from '@/lib/dashboard/types'

const SEGMENT_ACCENT: Readonly<Record<string, string>> = {
  swim: 'bg-sky-500',
  bike: 'bg-amber-500',
  run: 'bg-lime-500',
  transition: 'bg-muted-foreground',
}

function knownSport(sport: string): sport is Sport {
  return ['swim', 'bike', 'run', 'brick'].includes(sport)
}

function speed(entry: RaceTimelineEntry): string {
  if (!entry.distanceM || entry.durationS <= 0) return '—'
  const sport: Sport = knownSport(entry.sport) ? entry.sport : 'run'
  return formatSpeedForSport(sport, entry.distanceM / entry.durationS)
}

/** Le déroulé de l'épreuve, segment par segment, transitions comprises. */
export function RaceTimelineTable({ timeline }: { readonly timeline: RaceTimelineEntry[] }) {
  if (timeline.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        Aucun segment exploitable : la décomposition par discipline n’est pas encore disponible pour
        cette course.
      </p>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[36rem] text-sm">
        <thead>
          <tr className="text-muted-foreground text-left text-xs tracking-wide uppercase">
            <th className="pr-3 pb-2 font-medium">Segment</th>
            <th className="pr-3 pb-2 font-medium">Temps</th>
            <th className="pr-3 pb-2 font-medium">Part</th>
            <th className="pr-3 pb-2 font-medium">Distance</th>
            <th className="pr-3 pb-2 font-medium">Allure / vitesse</th>
            <th className="pb-2 font-medium">FC moy.</th>
          </tr>
        </thead>
        <tbody>
          {timeline.map((entry) => (
            <tr
              key={entry.key}
              className={cn(
                'border-border/60 border-t',
                entry.isTransition && 'text-muted-foreground'
              )}
            >
              <td className="py-2 pr-3 font-medium">
                <span className="flex items-center gap-2">
                  <span
                    aria-hidden
                    className={cn(
                      'size-2 rounded-full',
                      SEGMENT_ACCENT[entry.sport] ?? 'bg-muted-foreground'
                    )}
                  />
                  {entry.label}
                </span>
              </td>
              <td className="py-2 pr-3 tabular-nums">{formatRaceClock(entry.durationS)}</td>
              <td className="py-2 pr-3 tabular-nums">{entry.sharePct.toFixed(0)} %</td>
              <td className="py-2 pr-3">{formatDistanceFromMeters(entry.distanceM)}</td>
              <td className="py-2 pr-3">{entry.isTransition ? '—' : speed(entry)}</td>
              <td className="py-2">{entry.hrAvg ? `${String(entry.hrAvg)} bpm` : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
