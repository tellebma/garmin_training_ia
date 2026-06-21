'use client'

import { useState } from 'react'
import { Bike, Footprints, Waves, type LucideIcon } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { saveStepDispo } from '@/app/(app)/onboarding/actions'
import { previewPlan } from '@/lib/coach/duration-preview'
import { DAYS, DISPO_DEFAULTS, type DispoInput } from '@/lib/onboarding/schemas'

interface Props {
  initial: DispoInput
}

const DAY_LABEL: Record<(typeof DAYS)[number], string> = {
  mon: 'Lun',
  tue: 'Mar',
  wed: 'Mer',
  thu: 'Jeu',
  fri: 'Ven',
  sat: 'Sam',
  sun: 'Dim',
}

const SPORT_ICON: Record<'swim' | 'bike' | 'run', LucideIcon> = {
  swim: Waves,
  bike: Bike,
  run: Footprints,
}

export function DispoEditForm({ initial }: Readonly<Props>) {
  const [edit, setEdit] = useState(false)
  const [days, setDays] = useState<(typeof DAYS)[number][]>(
    initial.available_days ?? [...DISPO_DEFAULTS.available_days]
  )
  const [hours, setHours] = useState<string>(initial.hours_per_week?.toString() ?? '')
  const [swim, setSwim] = useState<number>(initial.sports_strengths?.swim ?? 3)
  const [bike, setBike] = useState<number>(initial.sports_strengths?.bike ?? 3)
  const [run, setRun] = useState<number>(initial.sports_strengths?.run ?? 3)
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState<Record<string, string[]>>({})

  function toggleDay(d: (typeof DAYS)[number]) {
    setDays((prev) => (prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d]))
  }

  function handleCancel() {
    setEdit(false)
    setDays(initial.available_days ?? [...DISPO_DEFAULTS.available_days])
    setHours(initial.hours_per_week?.toString() ?? '')
    setSwim(initial.sports_strengths?.swim ?? 3)
    setBike(initial.sports_strengths?.bike ?? 3)
    setRun(initial.sports_strengths?.run ?? 3)
    setErrors({})
  }

  const activeDaysLabels = days.map((d) => DAY_LABEL[d]).join(', ')

  if (!edit) {
    return (
      <section className="space-y-3 rounded-lg border p-6">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Disponibilité</h2>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setEdit(true)
            }}
          >
            Modifier
          </Button>
        </div>
        <dl className="text-muted-foreground grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
          <dt>Jours</dt>
          <dd className="text-foreground">{activeDaysLabels || '—'}</dd>
          <dt>H/semaine</dt>
          <dd className="text-foreground">{hours ? `${hours} h` : '—'}</dd>
          <dt>Niveau Swim / Bike / Run</dt>
          <dd className="text-foreground">
            {swim} / {bike} / {run}
          </dd>
        </dl>
      </section>
    )
  }

  async function handleSave() {
    setLoading(true)
    setErrors({})
    const r = await saveStepDispo({
      available_days: days.length > 0 ? days : undefined,
      hours_per_week: hours ? Number.parseInt(hours, 10) : undefined,
      sports_strengths: { swim, bike, run },
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

  const hoursNum = hours ? Number.parseInt(hours, 10) : 0
  const nAvailable = days.length
  const preview =
    hoursNum > 0 && nAvailable > 0
      ? previewPlan({ nAvailable, hours: hoursNum, strengths: { swim, bike, run } })
      : null

  return (
    <section className="space-y-4 rounded-lg border p-6">
      <h2 className="text-lg font-semibold">Disponibilité</h2>

      <div className="space-y-2">
        <Label>Jours dispo (clique pour sélectionner)</Label>
        <div className="flex flex-wrap gap-2">
          {DAYS.map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => {
                toggleDay(d)
              }}
              className={
                days.includes(d)
                  ? 'bg-primary text-primary-foreground rounded-md border px-3 py-1 text-sm'
                  : 'text-muted-foreground rounded-md border px-3 py-1 text-sm'
              }
            >
              {DAY_LABEL[d]}
            </button>
          ))}
        </div>
        <p className="text-muted-foreground text-xs">Vide → defaults : Lun-Mar-Mer-Jeu-Sam.</p>
      </div>

      <div className="space-y-2">
        <Label htmlFor="dispo-hours">Heures par semaine</Label>
        <Input
          id="dispo-hours"
          type="number"
          min={1}
          max={30}
          value={hours}
          onChange={(e) => {
            setHours(e.target.value)
          }}
          placeholder="ex: 6"
        />
        {errors.hours_per_week?.[0] && (
          <p className="text-destructive text-xs">{errors.hours_per_week[0]}</p>
        )}
      </div>

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Niveau par sport (1=faible, 5=fort)</legend>
        {(['swim', 'bike', 'run'] as const).map((sport) => {
          const sportValues = { swim, bike, run }
          const sportValue = sportValues[sport]
          const setters = { swim: setSwim, bike: setBike, run: setRun }
          return (
            <div key={sport} className="flex items-center gap-3 text-sm">
              <span className="w-12 capitalize">{sport}</span>
              <input
                type="range"
                min={1}
                max={5}
                value={sportValue}
                onChange={(e) => {
                  setters[sport](Number.parseInt(e.target.value, 10))
                }}
                className="flex-1"
              />
              <span className="w-6 text-right">{sportValue}</span>
            </div>
          )
        })}
      </fieldset>

      {preview && (
        <div className="bg-muted/40 space-y-1 rounded-md border p-3 text-sm">
          <p className="font-medium">Aperçu de tes séances types</p>
          <p className="text-muted-foreground text-xs">
            Tu te déclares dispo {nAvailable} jour(s) ; je programme {preview.trainingDays}{' '}
            séance(s) + {preview.restDays} repos.
          </p>
          <ul className="text-muted-foreground space-y-0.5 text-xs">
            {preview.disciplines.map((d) => {
              const Icon = SPORT_ICON[d.sport]
              return (
                <li key={d.sport} className="flex items-center gap-1.5">
                  <Icon className="size-3.5 shrink-0" aria-hidden />
                  <span className="capitalize">{d.sport}</span> endurance ~{d.enduranceMinLabel}
                </li>
              )
            })}
          </ul>
        </div>
      )}

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
