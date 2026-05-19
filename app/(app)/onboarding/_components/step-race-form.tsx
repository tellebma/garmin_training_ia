'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { saveStepRace } from '../actions'
import { RACE_DISTANCES, type RaceInput } from '@/lib/onboarding/schemas'
import type { Step } from '@/lib/onboarding/steps'

interface Props {
  defaultValues: RaceInput | null
  onDone: (nextStep: Step | null) => void
}

const DISTANCE_LABELS: Record<(typeof RACE_DISTANCES)[number], string> = {
  sprint: 'Sprint (~750/20/5)',
  olympique: 'Olympique (1500/40/10)',
  half_ironman: 'Half Ironman 70.3',
  ironman: 'Ironman 140.6',
  autre: 'Autre',
}

export function StepRaceForm({ defaultValues, onDone }: Readonly<Props>) {
  const [race_date, setRaceDate] = useState(defaultValues?.race_date ?? '')
  const [race_distance, setDistance] = useState<(typeof RACE_DISTANCES)[number]>(
    defaultValues?.race_distance ?? 'olympique'
  )
  const [name, setName] = useState(defaultValues?.name ?? '')
  const [location, setLocation] = useState(defaultValues?.location ?? '')
  const [target_hms, setTargetHms] = useState(
    defaultValues?.target_time_seconds ? secondsToHms(defaultValues.target_time_seconds) : ''
  )
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState<Record<string, string[]>>({})

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)
    setErrors({})
    const target_time_seconds = target_hms ? hmsToSeconds(target_hms) : undefined
    const result = await saveStepRace({
      race_date,
      race_distance,
      name: name || undefined,
      location: location || undefined,
      target_time_seconds,
    })
    setLoading(false)
    if (!result.success) {
      if ('errors' in result) {
        setErrors(result.errors as Record<string, string[]>)
        toast.error('Corrige les erreurs avant de continuer.')
      } else {
        toast.error('Erreur de sauvegarde, réessaye.')
      }
      return
    }
    onDone(result.nextStep)
  }

  return (
    <form
      onSubmit={(e) => {
        void handleSubmit(e)
      }}
      className="space-y-4"
      noValidate
    >
      <div className="space-y-2">
        <Label htmlFor="race_date">Date de la course</Label>
        <Input
          id="race_date"
          type="date"
          value={race_date}
          onChange={(e) => {
            setRaceDate(e.target.value)
          }}
          aria-invalid={Boolean(errors.race_date?.[0])}
        />
        {errors.race_date?.[0] && <p className="text-destructive text-xs">{errors.race_date[0]}</p>}
      </div>
      <div className="space-y-2">
        <Label htmlFor="race_distance">Distance</Label>
        <select
          id="race_distance"
          value={race_distance}
          onChange={(e) => {
            setDistance(e.target.value as (typeof RACE_DISTANCES)[number])
          }}
          className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
        >
          {RACE_DISTANCES.map((d) => (
            <option key={d} value={d}>
              {DISTANCE_LABELS[d]}
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-2">
        <Label htmlFor="name">
          Nom de la course
          <span className="text-muted-foreground ml-1 text-xs font-normal">(optionnel)</span>
        </Label>
        <Input
          id="name"
          value={name}
          onChange={(e) => {
            setName(e.target.value)
          }}
          placeholder="ex: Ironman 70.3 Nice"
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="location">
          Lieu
          <span className="text-muted-foreground ml-1 text-xs font-normal">(optionnel)</span>
        </Label>
        <Input
          id="location"
          value={location}
          onChange={(e) => {
            setLocation(e.target.value)
          }}
          placeholder="ex: Nice, France"
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="target_hms">
          Temps cible
          <span className="text-muted-foreground ml-1 text-xs font-normal">
            (optionnel, format hh:mm:ss)
          </span>
        </Label>
        <Input
          id="target_hms"
          value={target_hms}
          onChange={(e) => {
            setTargetHms(e.target.value)
          }}
          placeholder="05:30:00"
          pattern="^\d{1,2}:\d{2}:\d{2}$"
        />
      </div>
      <Button type="submit" disabled={loading} className="w-full">
        {loading ? 'Sauvegarde...' : 'Suivant'}
      </Button>
    </form>
  )
}

function hmsToSeconds(hms: string): number {
  const parts = hms.split(':').map((n) => Number.parseInt(n, 10))
  const h = parts[0] ?? 0
  const m = parts[1] ?? 0
  const s = parts[2] ?? 0
  return h * 3600 + m * 60 + s
}

function secondsToHms(total: number): string {
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}
