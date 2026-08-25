import { describe, expect, it, vi } from 'vitest'
import { countedActivities, excludedActivities } from '@/lib/activities/scope'

function fakeQuery() {
  const query = {
    is: vi.fn(() => query),
    not: vi.fn(() => query),
  }
  return query
}

describe('activities scope', () => {
  it('keeps only the activities that count', () => {
    const query = fakeQuery()

    expect(countedActivities(query)).toBe(query)
    expect(query.is).toHaveBeenCalledWith('excluded_at', null)
  })

  it('lists the deleted ones for the restore screen', () => {
    const query = fakeQuery()

    expect(excludedActivities(query)).toBe(query)
    expect(query.not).toHaveBeenCalledWith('excluded_at', 'is', null)
  })
})
