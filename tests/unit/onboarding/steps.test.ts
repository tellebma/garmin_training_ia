import { describe, it, expect } from 'vitest'
import { STEPS, STEP_LABELS, nextStep, type Step } from '@/lib/onboarding/steps'

describe('STEPS', () => {
  it('exposes the 4 onboarding steps in order', () => {
    expect(STEPS).toEqual(['perso', 'race', 'perf', 'dispo'])
  })

  it('each step has a French label', () => {
    for (const step of STEPS) {
      expect(STEP_LABELS[step]).toBeTruthy()
      expect(typeof STEP_LABELS[step]).toBe('string')
    }
  })
})

describe('nextStep', () => {
  it('returns the next step in sequence', () => {
    expect(nextStep('perso')).toBe('race')
    expect(nextStep('race')).toBe('perf')
    expect(nextStep('perf')).toBe('dispo')
  })

  it('returns null at the last step', () => {
    expect(nextStep('dispo')).toBeNull()
  })

  it('returns null for an unknown step (defensive)', () => {
    expect(nextStep('unknown' as Step)).toBeNull()
  })
})
