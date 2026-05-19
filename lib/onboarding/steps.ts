// lib/onboarding/steps.ts
export const STEPS = ['perso', 'race', 'perf', 'dispo'] as const
export type Step = (typeof STEPS)[number]

export const STEP_LABELS: Record<Step, string> = {
  perso: 'Informations personnelles',
  race: 'Course cible',
  perf: 'Performance',
  dispo: 'Disponibilité',
}

export function nextStep(current: Step): Step | null {
  const i = STEPS.indexOf(current)
  if (i >= 0 && i < STEPS.length - 1) {
    return STEPS[i + 1] ?? null
  }
  return null
}
