'use client'

import { useState } from 'react'
import Link from 'next/link'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { saveStepRace } from '@/app/(app)/onboarding/actions'
import {
  PARENT_DISCIPLINES,
  LEG_RULES,
  computeTotals,
  type Leg,
  type RaceInput,
} from '@/lib/onboarding/schemas'

interface Props {
  initial: RaceInput | null
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
  swim: '🏊',
  bike: '🚴',
  run: '🏃',
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

function RaceSummary({ race }: Readonly<{ race: RaceInput }>) {
  const totals = computeTotals(race.legs)
  return (
    <>
      <div className="text-sm font-medium">
        {race.name ?? PARENT_LABEL[race.discipline]} · {race.race_date}
      </div>
      <div className="text-muted-foreground mt-1 flex flex-wrap items-center gap-2 text-xs">
        {race.legs.map((l, i) => (
          <span key={`leg-${String(i)}`} className="inline-flex items-center gap-1">
            {LEG_ICON[l.discipline]} {l.distance_km} km
            {l.discipline !== 'swim' && ` · ${String(l.elevation_gain_m)} m`}
            {i < race.legs.length - 1 && <span className="mx-1">→</span>}
          </span>
        ))}
      </div>
      <div className="text-muted-foreground mt-2 text-xs">
        Total :{' '}
        <strong>
          {totals.total_distance_km.toFixed(1)} km · {String(totals.total_elevation_gain_m)} m D+
        </strong>
        {race.target_time_seconds && (
          <span> · Cible : {secondsToHms(race.target_time_seconds)}</span>
        )}
      </div>
    </>
  )
}

export function RaceEditForm({ initial }: Readonly<Props>) {
  const [edit, setEdit] = useState(false)
  const [raceDate, setRaceDate] = useState(initial?.race_date ?? '')
  const [discipline, setDiscipline] = useState<(typeof PARENT_DISCIPLINES)[number]>(
    initial?.discipline ?? 'triathlon'
  )
  const [name, setName] = useState(initial?.name ?? '')
  const [location, setLocation] = useState(initial?.location ?? '')
  const [targetHms, setTargetHms] = useState(
    initial?.target_time_seconds ? secondsToHms(initial.target_time_seconds) : ''
  )
  const [legs, setLegs] = useState<Leg[]>(initial?.legs ?? defaultLegsFor('triathlon'))
  const [loading, setLoading] = useState(false)

  const isAutre = discipline === 'autre'
  const totals = computeTotals(legs)

  function updateLeg(index: number, patch: Partial<Leg>) {
    setLegs((prev) =>
      prev.map((l, i) => {
        if (i !== index) return l
        const merged = { ...l, ...patch }
        // Force elevation_gain_m = 0 quand la discipline est natation.
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

  async function handleSave() {
    setLoading(true)
    const target_time_seconds = targetHms ? hmsToSeconds(targetHms) : undefined
    const r = await saveStepRace({
      race_date: raceDate,
      discipline,
      name: name || undefined,
      location: location || undefined,
      target_time_seconds,
      legs,
    })
    setLoading(false)
    if (!r.success) {
      toast.error('Erreur de sauvegarde')
      return
    }
    setEdit(false)
    toast.success('Sauvegardé')
  }

  if (!edit) {
    return (
      <section className="space-y-3 rounded-lg border p-6">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Course cible</h2>
          {initial ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setEdit(true)
              }}
            >
              Modifier
            </Button>
          ) : (
            <Button asChild variant="outline" size="sm">
              <Link href="/onboarding">Ajouter</Link>
            </Button>
          )}
        </div>
        {initial ? (
          <RaceSummary race={initial} />
        ) : (
          <p className="text-muted-foreground text-sm">Pas de course définie.</p>
        )}
      </section>
    )
  }

  return (
    <section className="space-y-4 rounded-lg border p-6">
      <h2 className="text-lg font-semibold">Course cible — édition</h2>

      <div className="space-y-2">
        <Label htmlFor="re-race_date">Date</Label>
        <Input
          id="re-race_date"
          type="date"
          value={raceDate}
          onChange={(e) => {
            setRaceDate(e.target.value)
          }}
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="re-discipline">Type</Label>
        <select
          id="re-discipline"
          value={discipline}
          onChange={(e) => {
            const d = e.target.value as (typeof PARENT_DISCIPLINES)[number]
            setDiscipline(d)
            if (d !== 'autre') {
              const matches = LEG_RULES[d].sequence?.every((s, i) => legs[i]?.discipline === s)
              if (!matches) setLegs(defaultLegsFor(d))
            }
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
        <Label htmlFor="re-name">
          Nom <span className="text-muted-foreground ml-1 text-xs font-normal">(optionnel)</span>
        </Label>
        <Input
          id="re-name"
          value={name}
          onChange={(e) => {
            setName(e.target.value)
          }}
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="re-location">
          Lieu <span className="text-muted-foreground ml-1 text-xs font-normal">(optionnel)</span>
        </Label>
        <Input
          id="re-location"
          value={location}
          onChange={(e) => {
            setLocation(e.target.value)
          }}
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="re-target">
          Temps cible{' '}
          <span className="text-muted-foreground ml-1 text-xs font-normal">
            (optionnel, hh:mm:ss)
          </span>
        </Label>
        <Input
          id="re-target"
          value={targetHms}
          onChange={(e) => {
            setTargetHms(e.target.value)
          }}
          placeholder="05:30:00"
        />
      </div>

      <div className="space-y-3 rounded-md border p-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">Segments</h3>
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
          <div key={`re-leg-${String(i)}`} className="rounded-md border p-3">
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm">
                <span>{String(i + 1)}.</span>
                {isAutre ? (
                  <select
                    value={leg.discipline}
                    onChange={(e) => {
                      updateLeg(i, { discipline: e.target.value as 'swim' | 'bike' | 'run' })
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
                <Label className="text-xs" htmlFor={`re-leg-${String(i)}-d`}>
                  Distance (km)
                </Label>
                <Input
                  id={`re-leg-${String(i)}-d`}
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
                  <Label className="text-xs" htmlFor={`re-leg-${String(i)}-e`}>
                    D+ (m)
                  </Label>
                  <Input
                    id={`re-leg-${String(i)}-e`}
                    type="number"
                    step="1"
                    min={0}
                    max={20000}
                    value={leg.elevation_gain_m || ''}
                    onChange={(e) => {
                      updateLeg(i, { elevation_gain_m: Number.parseInt(e.target.value, 10) || 0 })
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
        <Button
          variant="outline"
          onClick={() => {
            setEdit(false)
          }}
          disabled={loading}
        >
          Annuler
        </Button>
      </div>
    </section>
  )
}
