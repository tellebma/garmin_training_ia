'use client'

import { useState, useTransition } from 'react'
import { Bike, Footprints, Waves, type LucideIcon } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { finalizeOnboarding, saveStepDispo } from '../actions'
import { previewPlan } from '@/lib/coach/duration-preview'
import { DAYS, type DispoInput } from '@/lib/onboarding/schemas'
import type { Step } from '@/lib/onboarding/steps'

interface Props {
  defaultValues: DispoInput
  onDone: (nextStep: Step | null) => void
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

export function StepDispoForm({ defaultValues, onDone }: Readonly<Props>) {
  const [days, setDays] = useState<(typeof DAYS)[number][]>(defaultValues.available_days ?? [])
  const [hours, setHours] = useState<string>(defaultValues.hours_per_week?.toString() ?? '')
  const [swim, setSwim] = useState<number>(defaultValues.sports_strengths?.swim ?? 3)
  const [bike, setBike] = useState<number>(defaultValues.sports_strengths?.bike ?? 3)
  const [run, setRun] = useState<number>(defaultValues.sports_strengths?.run ?? 3)
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState<Record<string, string[]>>({})
  const [, startTransition] = useTransition()

  function toggleDay(d: (typeof DAYS)[number]) {
    setDays((prev) => (prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d]))
  }

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)
    setErrors({})
    const result = await saveStepDispo({
      available_days: days.length > 0 ? days : undefined,
      hours_per_week: hours ? Number.parseInt(hours, 10) : undefined,
      sports_strengths: { swim, bike, run },
    })
    if (!result.success) {
      setLoading(false)
      if ('errors' in result) {
        setErrors(result.errors as Record<string, string[]>)
        toast.error('Corrige les erreurs avant de continuer.')
      } else {
        toast.error('Erreur de sauvegarde, réessaye.')
      }
      return
    }
    // Last step → finalize (redirect to /profile)
    onDone(result.nextStep)
    startTransition(() => {
      void finalizeOnboarding()
    })
  }

  const hoursNum = hours ? Number.parseInt(hours, 10) : 0
  const nAvailable = days.length
  const preview =
    hoursNum > 0 && nAvailable > 0
      ? previewPlan({ nAvailable, hours: hoursNum, strengths: { swim, bike, run } })
      : null

  return (
    <form
      onSubmit={(e) => {
        void handleSubmit(e)
      }}
      className="space-y-4"
      noValidate
    >
      <div className="space-y-2">
        <Label>
          Jours dispo{' '}
          <span className="text-muted-foreground ml-1 text-xs font-normal">
            (optionnel — vide = Lun-Mar-Mer-Jeu-Sam)
          </span>
        </Label>
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
      </div>

      <div className="space-y-2">
        <Label htmlFor="hours">
          Heures par semaine{' '}
          <span className="text-muted-foreground ml-1 text-xs font-normal">
            (optionnel — vide = 6 h)
          </span>
        </Label>
        <Input
          id="hours"
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
          const setters = {
            swim: setSwim,
            bike: setBike,
            run: setRun,
          }
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

      <Button type="submit" disabled={loading} className="w-full">
        {loading ? 'Finalisation...' : "Terminer l'onboarding"}
      </Button>
    </form>
  )
}
