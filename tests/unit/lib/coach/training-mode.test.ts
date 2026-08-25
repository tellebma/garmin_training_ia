import { describe, expect, it } from 'vitest'
import {
  TRAINING_MODES,
  effectiveTrainingMode,
  isTrainingMode,
  trainingModeCopy,
} from '@/lib/coach/training-mode'

const TODAY = new Date('2026-08-25T10:00:00Z')

describe('isTrainingMode', () => {
  it.each(TRAINING_MODES)('accepte %s', (mode) => {
    expect(isTrainingMode(mode)).toBe(true)
  })

  it.each([null, undefined, '', 'RACE', 'rest', 42])('rejette %s', (value) => {
    expect(isTrainingMode(value)).toBe(false)
  })
})

describe('trainingModeCopy', () => {
  it('donne un libellé et une description à chaque mode', () => {
    for (const mode of TRAINING_MODES) {
      const copy = trainingModeCopy(mode)
      expect(copy.label.length).toBeGreaterThan(0)
      expect(copy.description.length).toBeGreaterThan(0)
    }
  })

  it('retombe sur la préparation course pour une valeur inconnue', () => {
    expect(trainingModeCopy('inconnu')).toEqual(trainingModeCopy('race'))
  })
})

describe('effectiveTrainingMode', () => {
  it('garde le cap déclaré quand ce n’est pas une préparation course', () => {
    expect(effectiveTrainingMode('maintain', null, TODAY)).toBe('maintain')
    expect(effectiveTrainingMode('improve', '2026-12-01', TODAY)).toBe('improve')
  })

  it('reste en préparation tant que la course est à venir', () => {
    expect(effectiveTrainingMode('race', '2026-08-26', TODAY)).toBe('race')
  })

  it('bascule en maintien dès le lendemain de la course', () => {
    // C'est le trou que E27 répare : ce jour-là, l'app ne produisait plus rien.
    expect(effectiveTrainingMode('race', '2026-08-24', TODAY)).toBe('maintain')
  })

  it('considère le jour de la course comme déjà couru', () => {
    expect(effectiveTrainingMode('race', '2026-08-25', TODAY)).toBe('maintain')
  })

  it('reste en préparation sans course renseignée (onboarding incomplet)', () => {
    expect(effectiveTrainingMode('race', null, TODAY)).toBe('race')
  })

  it('traite une valeur inconnue comme une préparation course', () => {
    expect(effectiveTrainingMode(null, '2026-12-01', TODAY)).toBe('race')
  })
})
