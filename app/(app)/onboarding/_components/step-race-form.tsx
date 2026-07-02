'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { saveStepRace } from '../actions'
import {
  PARENT_DISCIPLINES,
  LEG_RULES,
  computeTotals,
  type Leg,
  type RaceInput,
} from '@/lib/onboarding/schemas'
import type { Step } from '@/lib/onboarding/steps'

interface Props {
  defaultValues: RaceInput | null
  onDone: (nextStep: Step | null) => void
}

const PARENT_LABEL: Record<(typeof PARENT_DISCIPLINES)[number], string> = {
  triathlon: 'Triathlon',
  duathlon: 'Duathlon',
  aquathlon: 'Aquathlon',
  run: 'Course (route ou trail)',
  bike: 'Vélo',
  swim: 'Natation',
  autre: 'Autre / personnalisé',
}

type LegDiscipline = 'swim' | 'bike' | 'run'

const LEG_ICON: Record<LegDiscipline, string> = {
  swim: 'Nat.',
  bike: 'Vélo',
  run: 'Run',
}

const LEG_NAME: Record<LegDiscipline, string> = {
  swim: 'Natation',
  bike: 'Vélo',
  run: 'Course',
}

function defaultLegsFor(discipline: (typeof PARENT_DISCIPLINES)[number]): Leg[] {
  const rule = LEG_RULES[discipline]
  if (rule.sequence) {
    return rule.sequence.map((d, i) => ({
      order: i + 1,
      discipline: d,
      distance_km: 0,
      elevation_gain_m: 0,
    }))
  }
  return [{ order: 1, discipline: 'run', distance_km: 0, elevation_gain_m: 0 }]
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

export function StepRaceForm({ defaultValues, onDone }: Readonly<Props>) {
  const [raceDate, setRaceDate] = useState(defaultValues?.race_date ?? '')
  const [discipline, setDiscipline] = useState<(typeof PARENT_DISCIPLINES)[number]>(
    defaultValues?.discipline ?? 'triathlon'
  )
  const [name, setName] = useState(defaultValues?.name ?? '')
  const [location, setLocation] = useState(defaultValues?.location ?? '')
  const [targetHms, setTargetHms] = useState(
    defaultValues?.target_time_seconds ? secondsToHms(defaultValues.target_time_seconds) : ''
  )
  const [legs, setLegs] = useState<Leg[]>(
    defaultValues?.legs ?? defaultLegsFor(defaultValues?.discipline ?? 'triathlon')
  )
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState<Partial<Record<string, string[]>>>({})

  const isAutre = discipline === 'autre'
  const totals = computeTotals(legs)

  function updateLeg(index: number, patch: Partial<Leg>) {
    setLegs((prev) =>
      prev.map((l, i) => {
        if (i !== index) return l
        const merged = { ...l, ...patch }
        // Force elevation_gain_m = 0 quand la discipline du leg est natation
        // (pas de dénivelé en piscine ni open water, donc le champ est caché côté UI).
        if (merged.discipline === 'swim') merged.elevation_gain_m = 0
        return merged
      })
    )
  }

  function addLeg() {
    setLegs((prev) => [
      ...prev,
      { order: prev.length + 1, discipline: 'run', distance_km: 0, elevation_gain_m: 0 },
    ])
  }

  function removeLeg(index: number) {
    setLegs((prev) => prev.filter((_, i) => i !== index).map((l, i) => ({ ...l, order: i + 1 })))
  }

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)
    setErrors({})
    const target_time_seconds = targetHms ? hmsToSeconds(targetHms) : undefined
    const result = await saveStepRace({
      race_date: raceDate,
      discipline,
      name: name || undefined,
      location: location || undefined,
      target_time_seconds,
      legs,
    })
    setLoading(false)
    if (!result.success) {
      if ('errors' in result) {
        setErrors(result.errors)
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
          value={raceDate}
          onChange={(e) => {
            setRaceDate(e.target.value)
          }}
          aria-invalid={Boolean(errors.race_date?.[0])}
        />
        {errors.race_date?.[0] && <p className="text-destructive text-xs">{errors.race_date[0]}</p>}
      </div>

      <div className="space-y-2">
        <Label htmlFor="discipline">Type de course</Label>
        <select
          id="discipline"
          value={discipline}
          onChange={(e) => {
            const d = e.target.value as (typeof PARENT_DISCIPLINES)[number]
            setDiscipline(d)
            if (d !== 'autre') setLegs(defaultLegsFor(d))
          }}
          className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
        >
          {PARENT_DISCIPLINES.map((d) => (
            <option key={d} value={d}>
              {PARENT_LABEL[d]}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-2">
        <Label htmlFor="name">
          Nom de la course{' '}
          <span className="text-muted-foreground ml-1 text-xs font-normal">(optionnel)</span>
        </Label>
        <Input
          id="name"
          value={name}
          onChange={(e) => {
            setName(e.target.value)
          }}
          placeholder="ex: Triathlon de la Madeleine"
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="location">
          Lieu <span className="text-muted-foreground ml-1 text-xs font-normal">(optionnel)</span>
        </Label>
        <Input
          id="location"
          value={location}
          onChange={(e) => {
            setLocation(e.target.value)
          }}
          placeholder="ex: La Madeleine, FR"
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="target_hms">
          Temps cible total{' '}
          <span className="text-muted-foreground ml-1 text-xs font-normal">
            (optionnel, hh:mm:ss)
          </span>
        </Label>
        <Input
          id="target_hms"
          value={targetHms}
          onChange={(e) => {
            setTargetHms(e.target.value)
          }}
          placeholder="05:30:00"
          pattern="^\d{1,2}:\d{2}:\d{2}$"
        />
      </div>

      <div className="space-y-3 rounded-lg border p-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">
            Segments
            {!isAutre && ` (${String(legs.length)} pour ${PARENT_LABEL[discipline]})`}
          </h3>
          {isAutre && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={addLeg}
              disabled={legs.length >= 10}
            >
              + Ajouter
            </Button>
          )}
        </div>

        {legs.map((leg, i) => (
          <div key={`leg-${String(i)}`} className="rounded-md border p-3">
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm font-medium">
                <span>{String(i + 1)}.</span>
                {isAutre ? (
                  <select
                    value={leg.discipline}
                    onChange={(e) => {
                      updateLeg(i, {
                        discipline: e.target.value as 'swim' | 'bike' | 'run',
                      })
                    }}
                    className="border-input bg-background h-8 rounded-md border px-2 text-sm"
                  >
                    {(['swim', 'bike', 'run'] as const).map((d) => (
                      <option key={d} value={d}>
                        {LEG_ICON[d]} {LEG_NAME[d]}
                      </option>
                    ))}
                  </select>
                ) : (
                  <span>
                    {LEG_ICON[leg.discipline]} {LEG_NAME[leg.discipline]}
                  </span>
                )}
              </div>
              {isAutre && legs.length > 1 && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    removeLeg(i)
                  }}
                >
                  − Retirer
                </Button>
              )}
            </div>
            <div className={leg.discipline === 'swim' ? '' : 'grid grid-cols-2 gap-2'}>
              <div>
                <Label className="text-xs" htmlFor={`leg-${String(i)}-distance`}>
                  Distance (km)
                </Label>
                <Input
                  id={`leg-${String(i)}-distance`}
                  type="number"
                  step="0.01"
                  min={0}
                  max={1000}
                  value={leg.distance_km || ''}
                  onChange={(e) => {
                    updateLeg(i, { distance_km: Number.parseFloat(e.target.value) || 0 })
                  }}
                />
              </div>
              {leg.discipline !== 'swim' && (
                <div>
                  <Label className="text-xs" htmlFor={`leg-${String(i)}-elevation`}>
                    D+ (m)
                  </Label>
                  <Input
                    id={`leg-${String(i)}-elevation`}
                    type="number"
                    step="1"
                    min={0}
                    max={20000}
                    value={leg.elevation_gain_m || ''}
                    onChange={(e) => {
                      updateLeg(i, {
                        elevation_gain_m: Number.parseInt(e.target.value, 10) || 0,
                      })
                    }}
                  />
                </div>
              )}
            </div>
          </div>
        ))}

        <p className="text-muted-foreground border-t pt-2 text-xs">
          Total :{' '}
          <strong>
            {totals.total_distance_km.toFixed(1)} km · {String(totals.total_elevation_gain_m)} m D+
          </strong>
        </p>

        {errors.legs?.[0] && <p className="text-destructive text-xs">{errors.legs[0]}</p>}
      </div>

      <Button type="submit" disabled={loading} className="w-full">
        {loading ? 'Sauvegarde...' : 'Suivant'}
      </Button>
    </form>
  )
}
