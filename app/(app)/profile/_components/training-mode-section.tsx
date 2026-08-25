'use client'

import { useState, useTransition } from 'react'
import { toast } from 'sonner'
import { setTrainingMode } from '@/app/actions/training-mode'
import { TRAINING_MODES, trainingModeCopy, type TrainingMode } from '@/lib/coach/training-mode'

interface Props {
  /** Cap déclaré en base. */
  readonly current: TrainingMode
  /** Cap réellement appliqué au plan — diffère quand la course est déjà passée. */
  readonly effective: TrainingMode
  readonly hasUpcomingRace: boolean
}

/**
 * Changer de cap sans attendre la prochaine course (E27.5).
 *
 * « Préparation course » ne se choisit pas ici : elle se choisit en définissant une
 * épreuve, ce qui bascule le mode par trigger. Proposer le bouton sans course à
 * préparer promettrait un plan périodisé vers une date qui n'existe pas.
 */
export function TrainingModeSection({ current, effective, hasUpcomingRace }: Props) {
  const [mode, setMode] = useState<TrainingMode>(current)
  const [pending, startTransition] = useTransition()

  function choose(next: TrainingMode) {
    if (next === mode || pending) return
    const previous = mode
    setMode(next)
    startTransition(() => {
      void setTrainingMode(next).then((result) => {
        if (result.success) {
          toast.success(`Cap mis à jour : ${trainingModeCopy(next).label.toLowerCase()}`)
        } else {
          setMode(previous)
          toast.error('Le changement de cap n’a pas pu être enregistré.')
        }
      })
    })
  }

  const selectable = TRAINING_MODES.filter((m) => m !== 'race')

  return (
    <section className="space-y-3 rounded-lg border p-6">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Cap d’entraînement</h2>
        <span className="text-muted-foreground text-xs">{trainingModeCopy(effective).label}</span>
      </div>
      <p className="text-muted-foreground text-sm">{trainingModeCopy(effective).description}</p>

      {hasUpcomingRace ? (
        <p className="text-muted-foreground text-sm">
          Ton plan prépare ta prochaine course. Pour t’entraîner sans objectif daté, supprime ou
          reporte l’épreuve depuis la section « Course ».
        </p>
      ) : (
        <div className="space-y-2">
          {selectable.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => {
                choose(option)
              }}
              disabled={pending}
              aria-pressed={mode === option}
              className={`w-full rounded-md border p-3 text-left text-sm transition-colors ${
                mode === option ? 'border-foreground bg-muted' : 'hover:bg-muted/50'
              }`}
            >
              <span className="font-medium">{trainingModeCopy(option).label}</span>
              <span className="text-muted-foreground block text-xs">
                {trainingModeCopy(option).description}
              </span>
            </button>
          ))}
          <p className="text-muted-foreground text-xs">
            Pour repasser en préparation course, renseigne une épreuve à venir dans la section «
            Course » ci-dessous — le cap suit automatiquement.
          </p>
        </div>
      )}
    </section>
  )
}
