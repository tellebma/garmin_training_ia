'use client'

import { useState, useTransition, type SyntheticEvent } from 'react'
import { ChevronDown, Save } from 'lucide-react'
import { saveRaceResults, type RaceResultsInput } from '@/app/actions/race'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { formatRaceClock, parseRaceClock, type RaceResultsRow } from '@/lib/coach/race-analysis'

interface Props {
  readonly raceGoalId: string
  readonly initialResults: RaceResultsRow | null
}

type ClockField = 'officialTimeS' | 'swimTimeS' | 't1TimeS' | 'bikeTimeS' | 't2TimeS' | 'runTimeS'
type RankField = 'overallRank' | 'overallFinishers' | 'categoryRank' | 'categoryFinishers'
type TextField =
  | 'category'
  | 'bibNumber'
  | 'resultsUrl'
  | 'weather'
  | 'nutrition'
  | 'gear'
  | 'incidents'
  | 'comment'

const CLOCK_FIELDS: readonly { key: ClockField; label: string }[] = [
  { key: 'officialTimeS', label: 'Temps officiel' },
  { key: 'swimTimeS', label: 'Natation' },
  { key: 't1TimeS', label: 'T1' },
  { key: 'bikeTimeS', label: 'Vélo' },
  { key: 't2TimeS', label: 'T2' },
  { key: 'runTimeS', label: 'Course à pied' },
]

const RANK_FIELDS: readonly { key: RankField; label: string }[] = [
  { key: 'overallRank', label: 'Classement scratch' },
  { key: 'overallFinishers', label: 'Partants classés' },
  { key: 'categoryRank', label: 'Classement catégorie' },
  { key: 'categoryFinishers', label: 'Classés en catégorie' },
]

const TEXT_FIELDS: readonly { key: TextField; label: string; placeholder: string }[] = [
  { key: 'category', label: 'Catégorie', placeholder: 'S3, V1…' },
  { key: 'bibNumber', label: 'Dossard', placeholder: '187' },
  { key: 'resultsUrl', label: 'Lien résultats', placeholder: 'https://…' },
  { key: 'weather', label: 'Conditions', placeholder: '22 °C, vent de face sur le retour' },
  { key: 'nutrition', label: 'Nutrition', placeholder: '2 gels + 1 bidon iso' },
  { key: 'gear', label: 'Matériel', placeholder: 'Combinaison, roues profil bas' },
  { key: 'incidents', label: 'Incidents', placeholder: 'Crevaison, pénalité, coup de chaud…' },
  { key: 'comment', label: 'Ressenti', placeholder: 'Ce que tu retiens de cette course' },
]

function initialState(results: RaceResultsRow | null, raceGoalId: string): RaceResultsInput {
  return {
    raceGoalId,
    officialTimeS: results?.official_time_s ?? null,
    swimTimeS: results?.swim_time_s ?? null,
    t1TimeS: results?.t1_time_s ?? null,
    bikeTimeS: results?.bike_time_s ?? null,
    t2TimeS: results?.t2_time_s ?? null,
    runTimeS: results?.run_time_s ?? null,
    overallRank: results?.overall_rank ?? null,
    overallFinishers: results?.overall_finishers ?? null,
    category: results?.category ?? null,
    categoryRank: results?.category_rank ?? null,
    categoryFinishers: results?.category_finishers ?? null,
    bibNumber: results?.bib_number ?? null,
    resultsUrl: results?.results_url ?? null,
    weather: results?.weather ?? null,
    nutrition: results?.nutrition ?? null,
    gear: results?.gear ?? null,
    incidents: results?.incidents ?? null,
    comment: results?.comment ?? null,
  }
}

/**
 * Saisie des données que la montre n'a pas : chronos officiels, classement, contexte.
 * L'import depuis les plateformes de chronométrage (E23.5 V2) remplira les mêmes champs.
 */
export function RaceResultsForm({ raceGoalId, initialResults }: Readonly<Props>) {
  const [open, setOpen] = useState(initialResults === null)
  const [pending, startTransition] = useTransition()
  const [values, setValues] = useState<RaceResultsInput>(() =>
    initialState(initialResults, raceGoalId)
  )
  const [status, setStatus] = useState<'idle' | 'saved' | 'error'>('idle')

  function update<K extends keyof RaceResultsInput>(key: K, value: RaceResultsInput[K]): void {
    setStatus('idle')
    setValues((current) => ({ ...current, [key]: value }))
  }

  function submit(event: SyntheticEvent<HTMLFormElement>): void {
    event.preventDefault()
    startTransition(async () => {
      const result = await saveRaceResults(values)
      setStatus(result.success ? 'saved' : 'error')
    })
  }

  return (
    <section aria-labelledby="race-results-title" className="rounded-lg border p-4">
      <button
        type="button"
        className="flex w-full items-center justify-between text-left"
        aria-expanded={open}
        onClick={() => {
          setOpen((current) => !current)
        }}
      >
        <span>
          <span id="race-results-title" className="text-base font-semibold">
            Résultats officiels &amp; ressenti
          </span>
          <span className="text-muted-foreground mt-1 block text-sm">
            Chronos officiels, classement et contexte : ce que la montre ne mesure pas.
          </span>
        </span>
        <ChevronDown
          size={18}
          className={open ? 'rotate-180 transition-transform' : 'transition-transform'}
        />
      </button>

      {open && (
        <form className="mt-5 space-y-5" onSubmit={submit}>
          <fieldset className="grid gap-3 sm:grid-cols-3">
            <legend className="text-sm font-medium">Chronos (hh:mm:ss)</legend>
            {CLOCK_FIELDS.map((field) => (
              <label key={field.key} className="text-muted-foreground block text-xs">
                {field.label}
                <Input
                  className="mt-1"
                  inputMode="numeric"
                  placeholder="0:00:00"
                  defaultValue={
                    values[field.key] === null ? '' : formatRaceClock(values[field.key])
                  }
                  onBlur={(event) => {
                    update(field.key, parseRaceClock(event.target.value))
                  }}
                />
              </label>
            ))}
          </fieldset>

          <fieldset className="grid gap-3 sm:grid-cols-4">
            <legend className="text-sm font-medium">Classement</legend>
            {RANK_FIELDS.map((field) => (
              <label key={field.key} className="text-muted-foreground block text-xs">
                {field.label}
                <Input
                  className="mt-1"
                  inputMode="numeric"
                  defaultValue={values[field.key] ?? ''}
                  onBlur={(event) => {
                    const parsed = Number.parseInt(event.target.value, 10)
                    update(field.key, Number.isNaN(parsed) ? null : parsed)
                  }}
                />
              </label>
            ))}
          </fieldset>

          <fieldset className="grid gap-3 sm:grid-cols-2">
            <legend className="text-sm font-medium">Contexte</legend>
            {TEXT_FIELDS.map((field) => (
              <label key={field.key} className="text-muted-foreground block text-xs">
                {field.label}
                <Input
                  className="mt-1"
                  placeholder={field.placeholder}
                  defaultValue={values[field.key] ?? ''}
                  onBlur={(event) => {
                    update(field.key, event.target.value)
                  }}
                />
              </label>
            ))}
          </fieldset>

          <div className="flex items-center gap-3">
            <Button type="submit" disabled={pending}>
              <Save size={16} />
              {pending ? 'Enregistrement...' : 'Enregistrer'}
            </Button>
            {status === 'saved' && <span className="text-sm text-emerald-500">Enregistré</span>}
            {status === 'error' && (
              <span className="text-sm text-red-500">
                Enregistrement impossible — vérifie les chronos et le lien saisis.
              </span>
            )}
          </div>
        </form>
      )}
    </section>
  )
}
