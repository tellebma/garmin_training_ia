/**
 * Cap d'entraînement courant (E27).
 *
 * `race` est le mode historique (préparer une épreuve datée). Les deux autres existent
 * pour l'athlète qui n'a pas d'objectif : maintenir sa forme, ou progresser sans date.
 * La colonne `athlete_profiles.training_mode` est la source de vérité unique — créer un
 * objectif de course la repasse à `race` par trigger, dans la même transaction.
 */
export const TRAINING_MODES = ['race', 'maintain', 'improve'] as const

export type TrainingMode = (typeof TRAINING_MODES)[number]

interface TrainingModeCopy {
  readonly label: string
  readonly description: string
}

const COPY: Readonly<Record<TrainingMode, TrainingModeCopy>> = {
  race: {
    label: 'Préparation course',
    description: 'Le plan est périodisé vers la date de ton épreuve.',
  },
  maintain: {
    label: 'Maintien de forme',
    description: 'Charge stable, sans chercher à progresser — une semaine plus légère sur quatre.',
  },
  improve: {
    label: 'Progression continue',
    description:
      'Charge en hausse régulière, sans date d’objectif — une semaine allégée sur quatre.',
  },
}

export function isTrainingMode(value: unknown): value is TrainingMode {
  return typeof value === 'string' && (TRAINING_MODES as readonly string[]).includes(value)
}

export function trainingModeCopy(mode: unknown): TrainingModeCopy {
  return isTrainingMode(mode) ? COPY[mode] : COPY.race
}

/**
 * Le cap réellement appliqué, qui n'est pas toujours celui déclaré.
 *
 * Une course déjà courue sans nouveau cap choisi laisse `training_mode = 'race'` en base
 * — la question « et maintenant ? » reste posée (E26) — alors que le plan produit est un
 * plan de maintien. L'interface doit dire ce qui se passe vraiment, pas ce qui est écrit.
 */
export function effectiveTrainingMode(
  mode: unknown,
  raceDate: string | null | undefined,
  today: Date = new Date()
): TrainingMode {
  const declared = isTrainingMode(mode) ? mode : 'race'
  if (declared !== 'race') return declared
  if (!raceDate) return 'race'
  const race = new Date(`${raceDate}T00:00:00Z`)
  const midnight = new Date(
    Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate())
  )
  return race > midnight ? 'race' : 'maintain'
}
