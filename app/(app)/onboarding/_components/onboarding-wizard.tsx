'use client'

import { useState } from 'react'
import { STEPS, STEP_LABELS, type Step } from '@/lib/onboarding/steps'
import { StepPersoForm } from './step-perso-form'
import { StepRaceForm } from './step-race-form'
import { StepPerfForm } from './step-perf-form'
import { StepDispoForm } from './step-dispo-form'
import type { PersonInput, RaceInput, PerfInput, DispoInput } from '@/lib/onboarding/schemas'
import { cn } from '@/lib/utils'

export interface WizardInitial {
  perso: PersonInput | null
  race: RaceInput | null
  perf: PerfInput & { garmin_synced_at: string | null }
  dispo: DispoInput
}

interface Props {
  initial: WizardInitial
  initialStep: Step
}

export function OnboardingWizard({ initial, initialStep }: Readonly<Props>) {
  const [step, setStep] = useState<Step>(initialStep)
  const [completed, setCompleted] = useState<Set<Step>>(() => {
    const s = new Set<Step>()
    if (initial.perso) s.add('perso')
    if (initial.race) s.add('race')
    if (initial.perf.ftp_watts ?? initial.perf.vma_kmh ?? initial.perf.fc_max_bpm) s.add('perf')
    if (initial.dispo.hours_per_week) s.add('dispo')
    return s
  })

  function markDoneAndAdvance(done: Step, next: Step | null) {
    setCompleted((prev) => new Set(prev).add(done))
    if (next) setStep(next)
  }

  return (
    <section className="space-y-6">
      <nav aria-label="Étapes" className="flex flex-wrap gap-2 text-sm">
        {STEPS.map((s, i) => (
          <button
            key={s}
            type="button"
            onClick={() => {
              setStep(s)
            }}
            className={cn(
              'rounded-full border px-3 py-1 transition',
              step === s && 'bg-primary text-primary-foreground',
              completed.has(s) && step !== s && 'bg-emerald-500/10 text-emerald-600',
              !completed.has(s) && step !== s && 'text-muted-foreground'
            )}
          >
            {completed.has(s) && step !== s ? '✓ ' : `${String(i + 1)}. `}
            {STEP_LABELS[s]}
          </button>
        ))}
      </nav>

      <div className="rounded-lg border p-6">
        {step === 'perso' && (
          <StepPersoForm
            defaultValues={initial.perso}
            onDone={(next) => {
              markDoneAndAdvance('perso', next)
            }}
          />
        )}
        {step === 'race' && (
          <StepRaceForm
            defaultValues={initial.race}
            onDone={(next) => {
              markDoneAndAdvance('race', next)
            }}
          />
        )}
        {step === 'perf' && (
          <StepPerfForm
            defaultValues={initial.perf}
            onDone={(next) => {
              markDoneAndAdvance('perf', next)
            }}
          />
        )}
        {step === 'dispo' && (
          <StepDispoForm
            defaultValues={initial.dispo}
            onDone={(next) => {
              markDoneAndAdvance('dispo', next)
            }}
          />
        )}
      </div>
    </section>
  )
}
