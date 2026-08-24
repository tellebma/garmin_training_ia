'use client'

import { useState, useTransition } from 'react'
import Link from 'next/link'
import { Flag, X } from 'lucide-react'
import { createRetroactiveRace, tagActivityAsRace, untagActivityRace } from '@/app/actions/race'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

export interface CandidateRace {
  readonly id: string
  readonly name: string | null
  readonly discipline: string
}

interface Props {
  readonly activityId: string
  readonly activityDate: string
  readonly activitySport: string
  readonly race: CandidateRace | null
  readonly candidates: readonly CandidateRace[]
}

const DISCIPLINES = [
  { value: 'triathlon', label: 'Triathlon' },
  { value: 'duathlon', label: 'Duathlon' },
  { value: 'aquathlon', label: 'Aquathlon' },
  { value: 'run', label: 'Course à pied' },
  { value: 'bike', label: 'Vélo' },
  { value: 'swim', label: 'Natation' },
  { value: 'autre', label: 'Autre' },
] as const

function defaultDiscipline(sport: string): string {
  const known = DISCIPLINES.find((discipline) => discipline.value === sport)
  return known ? known.value : 'triathlon'
}

/**
 * Marquer une activité comme course, ou l'en retirer. La détection automatique ne
 * couvre que les épreuves saisies comme objectif : tout le reste passe par ici.
 */
export function RaceTagForm({
  activityId,
  activityDate,
  activitySport,
  race,
  candidates,
}: Readonly<Props>) {
  const [pending, startTransition] = useTransition()
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const [discipline, setDiscipline] = useState(() => defaultDiscipline(activitySport))
  const [error, setError] = useState<string | null>(null)

  function run(action: () => Promise<{ success: boolean; error?: string }>): void {
    setError(null)
    startTransition(async () => {
      const result = await action()
      if (!result.success) setError('Action impossible pour le moment.')
      else setCreating(false)
    })
  }

  if (race) {
    return (
      <section className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4">
        <p className="flex items-center gap-2 text-sm font-semibold">
          <Flag size={16} /> Cette activité fait partie d’une course
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-3 text-sm">
          <Link href={`/history/race/${race.id}`} className="text-primary hover:underline">
            Voir la vue course{race.name ? ` — ${race.name}` : ''}
          </Link>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={pending}
            onClick={() => {
              run(() => untagActivityRace(activityId))
            }}
          >
            <X size={14} /> Ce n’est pas une course
          </Button>
        </div>
        {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
      </section>
    )
  }

  return (
    <section className="rounded-lg border p-4">
      <p className="text-sm font-semibold">C’était une course ?</p>
      <p className="text-muted-foreground mt-1 text-sm">
        Une activité taguée course ouvre la vue course : splits, transitions, débrief et comparaison
        aux épreuves précédentes.
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {candidates.map((candidate) => (
          <Button
            key={candidate.id}
            type="button"
            variant="outline"
            size="sm"
            disabled={pending}
            onClick={() => {
              run(() => tagActivityAsRace({ activityId, raceGoalId: candidate.id }))
            }}
          >
            <Flag size={14} /> {candidate.name ?? 'Course du jour'}
          </Button>
        ))}
        <Button
          type="button"
          variant={candidates.length > 0 ? 'ghost' : 'outline'}
          size="sm"
          disabled={pending}
          onClick={() => {
            setCreating((current) => !current)
          }}
        >
          Créer une course pour cette date
        </Button>
      </div>

      {creating && (
        <form
          className="mt-3 flex flex-wrap items-end gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            run(() =>
              createRetroactiveRace({
                activityId,
                name,
                raceDate: activityDate,
                discipline: discipline as (typeof DISCIPLINES)[number]['value'],
                location: null,
              })
            )
          }}
        >
          <label className="text-muted-foreground text-xs">
            Nom de l’épreuve
            <Input
              className="mt-1"
              value={name}
              required
              maxLength={120}
              onChange={(event) => {
                setName(event.target.value)
              }}
            />
          </label>
          <label className="text-muted-foreground text-xs">
            Discipline
            <select
              className="border-input bg-background mt-1 block h-9 rounded-md border px-2 text-sm"
              value={discipline}
              onChange={(event) => {
                setDiscipline(event.target.value)
              }}
            >
              {DISCIPLINES.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <Button type="submit" size="sm" disabled={pending || name.trim() === ''}>
            Enregistrer
          </Button>
        </form>
      )}

      {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
    </section>
  )
}
