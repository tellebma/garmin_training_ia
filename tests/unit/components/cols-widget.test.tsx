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
    type: 'col',
    ...overrides,
  }
}

describe('ColsWidget', () => {
  it('renders one row per col with name, altitude, distance and count', () => {
    render(<ColsWidget cols={[mkSummary({})]} peaks={[]} />)
    expect(screen.getByText('Col du Truc')).not.toBeNull()
    expect(screen.getByText(/1850/)).not.toBeNull()
    expect(screen.getByText(/12/)).not.toBeNull()
    expect(screen.getByText(/4 fois/)).not.toBeNull()
  })

  it('shows singular wording for exactly one crossing', () => {
    render(<ColsWidget cols={[mkSummary({ crossingsCount: 1 })]} peaks={[]} />)
    expect(screen.getByText(/1 fois/)).not.toBeNull()
  })

  it('shows a combined empty state when there are no cols and no peaks', () => {
    render(<ColsWidget cols={[]} peaks={[]} />)
    expect(screen.getByText(/Aucun col ni sommet recensé/)).not.toBeNull()
    expect(
      screen.getByText(/Aucun col ni sommet dans un rayon de 50 km autour de chez toi/)
    ).not.toBeNull()
  })

  it('renders only the peaks section when there are no cols', () => {
    render(
      <ColsWidget
        cols={[]}
        peaks={[mkSummary({ id: 'peak-1', name: 'Crêt du Machin', type: 'peak' })]}
      />
    )
    expect(screen.getByText('Sommets')).not.toBeNull()
    expect(screen.queryByText('Cols')).toBeNull()
    expect(screen.getByText('Crêt du Machin')).not.toBeNull()
  })

  it('renders both sections when cols and peaks are present', () => {
    render(
      <ColsWidget
        cols={[mkSummary({ id: 'col-1', name: 'Col du Truc' })]}
        peaks={[mkSummary({ id: 'peak-1', name: 'Crêt du Machin', type: 'peak' })]}
      />
    )
    expect(screen.getByText('Cols')).not.toBeNull()
    expect(screen.getByText('Sommets')).not.toBeNull()
  })

  it('shows all rows unfolded when there are 10 or fewer', () => {
    const summaries = Array.from({ length: 10 }, (_, i) =>
      mkSummary({ id: `col-${String(i)}`, name: `Col ${String(i)}` })
    )
    render(<ColsWidget cols={summaries} peaks={[]} />)
    expect(screen.getAllByRole('row')).toHaveLength(11) // 10 data rows + header
    expect(screen.queryByText(/Afficher les/)).toBeNull()
  })

  it('truncates past 10 rows behind a details/summary toggle', () => {
    const summaries = Array.from({ length: 13 }, (_, i) =>
      mkSummary({ id: `col-${String(i)}`, name: `Col ${String(i)}` })
    )
    render(<ColsWidget cols={summaries} peaks={[]} />)
    expect(screen.getByText('Col 0')).not.toBeNull()
    expect(screen.getByText('Col 9')).not.toBeNull()
    expect(screen.getByText('Afficher les 3 autres')).not.toBeNull()
    expect(screen.getByText('Col 12')).not.toBeNull()
  })
})
