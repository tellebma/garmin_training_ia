'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { saveStepRace } from '@/app/(app)/onboarding/actions'
import { RACE_DISTANCES, type RaceInput } from '@/lib/onboarding/schemas'

interface Props {
  initial: RaceInput | null
}

const DISTANCE_LABELS: Record<(typeof RACE_DISTANCES)[number], string> = {
  sprint: 'Sprint (~750/20/5)',
  olympique: 'Olympique (1500/40/10)',
  half_ironman: 'Half Ironman 70.3',
  ironman: 'Ironman 140.6',
  autre: 'Autre',
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

const EMPTY_RACE: RaceInput = {
  race_date: '',
  race_distance: 'olympique',
}

function RaceSummary({ race }: Readonly<{ race: RaceInput }>) {
  const parts = [DISTANCE_LABELS[race.race_distance], race.race_date]
  if (race.name) parts.push(race.name)
  if (race.location) parts.push(race.location)
  if (race.target_time_seconds) parts.push(`Objectif : ${secondsToHms(race.target_time_seconds)}`)
  return <p className="text-muted-foreground text-sm">{parts.join(' · ')}</p>
}

export function RaceEditForm({ initial }: Readonly<Props>) {
  const [edit, setEdit] = useState(false)
  const [values, setValues] = useState<RaceInput>(initial ?? EMPTY_RACE)
  const [targetHms, setTargetHms] = useState(
    initial?.target_time_seconds ? secondsToHms(initial.target_time_seconds) : ''
  )
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState<Record<string, string[]>>({})

  function handleCancel() {
    setEdit(false)
    setValues(initial ?? EMPTY_RACE)
    setTargetHms(initial?.target_time_seconds ? secondsToHms(initial.target_time_seconds) : '')
    setErrors({})
  }

  if (!edit) {
    return (
      <section className="space-y-3 rounded-lg border p-6">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Course cible</h2>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setEdit(true)
            }}
          >
            {initial ? 'Modifier' : 'Ajouter'}
          </Button>
        </div>
        {initial ? (
          <RaceSummary race={initial} />
        ) : (
          <p className="text-muted-foreground text-sm">Pas de course définie</p>
        )}
      </section>
    )
  }

  async function handleSave() {
    setLoading(true)
    setErrors({})
    const target_time_seconds = targetHms ? hmsToSeconds(targetHms) : undefined
    const r = await saveStepRace({
      ...values,
      target_time_seconds,
    })
    setLoading(false)
    if (!r.success) {
      if ('errors' in r) setErrors(r.errors as Record<string, string[]>)
      else toast.error('Erreur de sauvegarde, réessaye')
      return
    }
    setEdit(false)
    toast.success('Sauvegardé')
  }

  return (
    <section className="space-y-4 rounded-lg border p-6">
      <h2 className="text-lg font-semibold">Course cible</h2>

      <div className="space-y-2">
        <Label htmlFor="race-date">Date de la course</Label>
        <Input
          id="race-date"
          type="date"
          value={values.race_date}
          onChange={(e) => {
            setValues((v) => ({ ...v, race_date: e.target.value }))
          }}
        />
        {errors.race_date?.[0] && <p className="text-destructive text-xs">{errors.race_date[0]}</p>}
      </div>

      <div className="space-y-2">
        <Label htmlFor="race-distance">Distance</Label>
        <select
          id="race-distance"
          value={values.race_distance}
          onChange={(e) => {
            setValues((v) => ({
              ...v,
              race_distance: e.target.value as (typeof RACE_DISTANCES)[number],
            }))
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
        <Label htmlFor="race-name">Nom de la course (optionnel)</Label>
        <Input
          id="race-name"
          value={values.name ?? ''}
          onChange={(e) => {
            setValues((v) => ({ ...v, name: e.target.value || undefined }))
          }}
          placeholder="ex: Ironman 70.3 Nice"
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="race-location">Lieu (optionnel)</Label>
        <Input
          id="race-location"
          value={values.location ?? ''}
          onChange={(e) => {
            setValues((v) => ({ ...v, location: e.target.value || undefined }))
          }}
          placeholder="ex: Nice, France"
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="race-target">Temps cible (optionnel, format hh:mm:ss)</Label>
        <Input
          id="race-target"
          value={targetHms}
          onChange={(e) => {
            setTargetHms(e.target.value)
          }}
          placeholder="05:30:00"
          pattern="^\d{1,2}:\d{2}:\d{2}$"
        />
        {errors.target_time_seconds?.[0] && (
          <p className="text-destructive text-xs">{errors.target_time_seconds[0]}</p>
        )}
      </div>

      <div className="flex gap-2">
        <Button
          onClick={() => {
            void handleSave()
          }}
          disabled={loading}
        >
          {loading ? 'Sauvegarde...' : 'Enregistrer'}
        </Button>
        <Button variant="outline" onClick={handleCancel} disabled={loading}>
          Annuler
        </Button>
      </div>
    </section>
  )
}
