// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { ColsWidget } from '@/app/(app)/_components/cols-widget'
import type { ColSummary } from '@/lib/dashboard/cols'

afterEach(() => {
  cleanup()
})

function mkSummary(overrides: Partial<ColSummary>): ColSummary {
  return {
    id: 'col-1',
    name: 'Col du Truc',
    elevationM: 1850,
    distanceKm: 12,
    crossingsCount: 4,
    lastCrossedAt: '2026-06-15T08:00:00Z',
    ...overrides,
  }
}

describe('ColsWidget', () => {
  it('renders one row per col with name, altitude, distance and count', () => {
    render(<ColsWidget summaries={[mkSummary({})]} />)
    expect(screen.getByText('Col du Truc')).not.toBeNull()
    expect(screen.getByText(/1850/)).not.toBeNull()
    expect(screen.getByText(/12/)).not.toBeNull()
    expect(screen.getByText(/4 fois/)).not.toBeNull()
  })

  it('shows singular wording for exactly one crossing', () => {
    render(<ColsWidget summaries={[mkSummary({ crossingsCount: 1 })]} />)
    expect(screen.getByText(/1 fois/)).not.toBeNull()
  })

  it('shows an empty state when there are no cols in range', () => {
    render(<ColsWidget summaries={[]} />)
    expect(screen.getByText(/Aucun col recensé/)).not.toBeNull()
  })
})
