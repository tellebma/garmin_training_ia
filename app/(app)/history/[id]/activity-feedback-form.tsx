'use client'

import { useState, useTransition, type SyntheticEvent } from 'react'
import { Check, Save } from 'lucide-react'
import { saveActivityFeedback, type ActivityFeedbackInput } from '@/app/actions/activity-feedback'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import type { ActivityFeedbackDto, PerceivedDifficulty } from '@/lib/dashboard/types'

interface Props {
  readonly activityId: string
  readonly durationSeconds: number | null
  readonly initialFeedback: ActivityFeedbackDto | null
}

interface ScaleProps {
  readonly label: string
  readonly value: number | null
  readonly max: number
  readonly optional?: boolean
  readonly onChange: (value: number | null) => void
}

const difficultyOptions: readonly {
  value: PerceivedDifficulty
  label: string
}[] = [
  { value: 'easier', label: 'Plus facile' },
  { value: 'as_expected', label: 'Conforme' },
  { value: 'harder', label: 'Plus difficile' },
]

function ScaleControl({ label, value, max, optional = true, onChange }: Readonly<ScaleProps>) {
  return (
    <fieldset>
      <legend className="text-sm font-medium">
        {label}
        {optional && <span className="text-muted-foreground font-normal"> (facultatif)</span>}
      </legend>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {Array.from({ length: max }, (_, index) => index + 1).map((option) => (
          <button
            key={option}
            type="button"
            aria-pressed={value === option}
            onClick={() => {
              onChange(value === option && optional ? null : option)
            }}
            className={cn(
              'focus-visible:ring-ring size-8 rounded-md border text-xs font-medium transition-colors outline-none focus-visible:ring-2',
              value === option
                ? 'border-primary bg-primary text-primary-foreground'
                : 'bg-background hover:bg-accent'
            )}
          >
            {option}
          </button>
        ))}
      </div>
    </fieldset>
  )
}

function initialValue(feedback: ActivityFeedbackDto | null): ActivityFeedbackInput {
  return {
    activityId: feedback?.activity_id ?? '',
    rpe: feedback?.rpe ?? 5,
    fatigue: feedback?.fatigue ?? null,
    soreness: feedback?.soreness ?? null,
    pain: feedback?.pain ?? null,
    mood: feedback?.mood ?? null,
    perceivedDifficulty: feedback?.perceived_difficulty ?? null,
    painArea: feedback?.pain_area ?? null,
    comment: feedback?.comment ?? null,
  }
}

function submitLabel(pending: boolean, existing: boolean): string {
  if (pending) return 'Enregistrement...'
  return existing ? 'Mettre à jour' : 'Enregistrer'
}

export function ActivityFeedbackForm({
  activityId,
  durationSeconds,
  initialFeedback,
}: Readonly<Props>) {
  const [pending, startTransition] = useTransition()
  const [feedback, setFeedback] = useState<ActivityFeedbackInput>(() => ({
    ...initialValue(initialFeedback),
    activityId,
  }))
  const [status, setStatus] = useState<'idle' | 'saved' | 'error'>('idle')
  const sessionLoad = durationSeconds ? Math.round((durationSeconds / 60) * feedback.rpe) : null

  function update<K extends keyof ActivityFeedbackInput>(
    key: K,
    value: ActivityFeedbackInput[K]
  ): void {
    setStatus('idle')
    setFeedback((current) => ({ ...current, [key]: value }))
  }

  function submit(event: SyntheticEvent<HTMLFormElement>): void {
    event.preventDefault()
    setStatus('idle')
    startTransition(async () => {
      const result = await saveActivityFeedback(feedback)
      setStatus(result.success ? 'saved' : 'error')
    })
  }

  return (
    <section aria-labelledby="feedback-title" className="border-y py-5">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-muted-foreground text-xs font-medium uppercase">
            Ressenti post-séance
          </p>
          <h2 id="feedback-title" className="mt-1 text-base font-semibold">
            Comment l’effort a-t-il été vécu ?
          </h2>
          <p className="text-muted-foreground mt-1 max-w-2xl text-sm">
            Ton ressenti complète les données Garmin et aide le coach à interpréter la charge.
          </p>
        </div>
        {sessionLoad !== null && (
          <div className="bg-muted rounded-md px-3 py-2 text-sm">
            <span className="text-muted-foreground">Charge ressentie </span>
            <strong>{sessionLoad} u.a.</strong>
          </div>
        )}
      </div>

      <form className="mt-5 space-y-5" onSubmit={submit}>
        <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr_1fr]">
          <ScaleControl
            label="Effort global (RPE)"
            value={feedback.rpe}
            max={10}
            optional={false}
            onChange={(value) => {
              update('rpe', value ?? 5)
            }}
          />
          <ScaleControl
            label="Fatigue"
            value={feedback.fatigue}
            max={5}
            onChange={(value) => {
              update('fatigue', value)
            }}
          />
          <ScaleControl
            label="Courbatures"
            value={feedback.soreness}
            max={5}
            onChange={(value) => {
              update('soreness', value)
            }}
          />
          <ScaleControl
            label="Douleur ou gêne"
            value={feedback.pain}
            max={5}
            onChange={(value) => {
              update('pain', value)
            }}
          />
          <ScaleControl
            label="Humeur / motivation"
            value={feedback.mood}
            max={5}
            onChange={(value) => {
              update('mood', value)
            }}
          />
          <fieldset>
            <legend className="text-sm font-medium">Par rapport au prévu</legend>
            <div className="mt-2 inline-flex flex-wrap gap-1 rounded-md border p-1">
              {difficultyOptions.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  aria-pressed={feedback.perceivedDifficulty === option.value}
                  onClick={() => {
                    update('perceivedDifficulty', option.value)
                  }}
                  className={cn(
                    'rounded px-2.5 py-1.5 text-xs font-medium transition-colors',
                    feedback.perceivedDifficulty === option.value
                      ? 'bg-primary text-primary-foreground'
                      : 'hover:bg-accent'
                  )}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </fieldset>
        </div>

        {feedback.pain !== null && feedback.pain > 0 && (
          <div className="max-w-md">
            <label htmlFor="pain-area" className="text-sm font-medium">
              Zone concernée
            </label>
            <Input
              id="pain-area"
              value={feedback.painArea ?? ''}
              maxLength={120}
              onChange={(event) => {
                update('painArea', event.target.value)
              }}
              className="mt-2"
              placeholder="Ex. genou droit"
            />
          </div>
        )}

        <div>
          <label htmlFor="feedback-comment" className="text-sm font-medium">
            Note libre <span className="text-muted-foreground font-normal">(facultatif)</span>
          </label>
          <textarea
            id="feedback-comment"
            value={feedback.comment ?? ''}
            maxLength={500}
            rows={3}
            onChange={(event) => {
              update('comment', event.target.value)
            }}
            className="border-input focus-visible:border-ring focus-visible:ring-ring/50 mt-2 block w-full max-w-2xl resize-y rounded-md border bg-transparent px-3 py-2 text-sm outline-none focus-visible:ring-3"
            placeholder="Sensations, contexte ou détail utile pour le prochain entraînement."
          />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" disabled={pending}>
            <Save />
            {submitLabel(pending, initialFeedback !== null)}
          </Button>
          {status === 'saved' && (
            <p
              role="status"
              className="text-muted-foreground inline-flex items-center gap-1 text-sm"
            >
              <Check className="text-emerald-600" size={16} />
              Ressenti enregistré
            </p>
          )}
          {status === 'error' && (
            <p role="alert" className="text-destructive text-sm">
              Enregistrement impossible. Réessaie dans un instant.
            </p>
          )}
        </div>
      </form>
    </section>
  )
}
