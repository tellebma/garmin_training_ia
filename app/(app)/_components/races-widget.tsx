import Link from 'next/link'
import { Flag } from 'lucide-react'
import { formatClockDelta, formatRaceClock, type RaceHistoryEntry } from '@/lib/coach/race-analysis'
import { ChartCard } from './chart-card'
import { EmptyState } from './empty-state'

const DISCIPLINE_LABEL: Readonly<Record<string, string>> = {
  triathlon: 'Triathlon',
  duathlon: 'Duathlon',
  aquathlon: 'Aquathlon',
  run: 'Course à pied',
  bike: 'Vélo',
  swim: 'Natation',
  autre: 'Course',
}

function deltaClass(delta: number): string {
  return delta <= 0 ? 'text-emerald-500' : 'text-red-500'
}

/** Les courses comme jalons de progression : temps, écart à l'objectif, écart à la précédente. */
export function RacesWidget({ races }: { readonly races: readonly RaceHistoryEntry[] }) {
  return (
    <ChartCard
      title="Mes courses"
      description="Chaque épreuve, son temps et sa progression par rapport à la précédente."
    >
      {races.length === 0 ? (
        <EmptyState
          icon={Flag}
          title="Aucune course enregistrée"
          description="Une activité taguée course apparaîtra ici, avec son temps et sa progression."
        />
      ) : (
        <ul className="divide-border/60 divide-y">
          {races.map((race) => (
            <li key={race.raceGoalId} className="flex items-center justify-between gap-3 py-3">
              <div className="min-w-0">
                <Link
                  href={`/history/race/${race.raceGoalId}`}
                  className="truncate text-sm font-medium hover:underline"
                >
                  {race.name}
                </Link>
                <p className="text-muted-foreground mt-0.5 text-xs">
                  {new Date(`${race.raceDate}T00:00:00Z`).toLocaleDateString('fr-FR', {
                    day: 'numeric',
                    month: 'short',
                    year: 'numeric',
                    timeZone: 'UTC',
                  })}{' '}
                  · {DISCIPLINE_LABEL[race.discipline] ?? race.discipline}
                </p>
              </div>
              <div className="text-right text-xs">
                <p className="text-foreground text-sm font-medium tabular-nums">
                  {formatRaceClock(race.elapsedS)}
                </p>
                <p className="text-muted-foreground mt-0.5 flex items-center justify-end gap-2">
                  {race.previousDeltaS !== null && (
                    <span className={deltaClass(race.previousDeltaS)}>
                      {formatClockDelta(race.previousDeltaS)} vs précédente
                    </span>
                  )}
                  {race.targetDeltaS !== null && (
                    <span className={deltaClass(race.targetDeltaS)}>
                      {formatClockDelta(race.targetDeltaS)} / objectif
                    </span>
                  )}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </ChartCard>
  )
}
