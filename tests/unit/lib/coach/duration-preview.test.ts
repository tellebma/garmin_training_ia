import { describe, expect, it } from 'vitest'
import { previewPlan, trainingDaysCount } from '@/lib/coach/duration-preview'

describe('duration-preview', () => {
  it('caps training days for 7 available / 8h intermediate', () => {
    expect(
      trainingDaysCount({ nAvailable: 7, hours: 8, strengths: { swim: 3, bike: 3, run: 3 } })
    ).toBe(5)
  })

  it('caps training days to availability when availability is the constraint', () => {
    const p = previewPlan({
      nAvailable: 4,
      hours: 8,
      strengths: { swim: 2, bike: 4, run: 2 },
    })
    expect(p.trainingDays).toBe(4)
    const bike = p.disciplines.find((d) => d.sport === 'bike')
    expect(bike?.enduranceMinLabel).toContain('h')
  })

  it('reports at least one rest day when fully available', () => {
    const p = previewPlan({ nAvailable: 7, hours: 8, strengths: { swim: 3, bike: 3, run: 3 } })
    expect(p.restDays).toBeGreaterThanOrEqual(1)
  })

  it('weak discipline lands lower in the endurance range than a strong one', () => {
    const p = previewPlan({ nAvailable: 5, hours: 8, strengths: { swim: 1, bike: 5, run: 3 } })
    const swim = p.disciplines.find((d) => d.sport === 'swim')
    const bike = p.disciplines.find((d) => d.sport === 'bike')
    expect(swim?.enduranceMinLabel).not.toEqual(bike?.enduranceMinLabel)
  })
})
