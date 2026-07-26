// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
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

  it('shows a combined empty state when the list is empty', () => {
    render(<ColsWidget summaries={[]} />)
    expect(screen.getByText(/Aucun col ni sommet recensé/)).not.toBeNull()
    expect(
      screen.getByText(/Aucun col ni sommet dans un rayon de 50 km autour de chez toi/)
    ).not.toBeNull()
  })

  it('renders cols and peaks in the same single list, with a badge on peaks', () => {
    // Décision owner 2026-07-26 : plus de sections séparées.
    render(
      <ColsWidget
        summaries={[
          mkSummary({ id: 'col-1', name: 'Col du Truc' }),
          mkSummary({ id: 'peak-1', name: 'Crêt du Machin', type: 'peak' }),
        ]}
      />
    )
    expect(screen.queryByText('Cols')).toBeNull()
    expect(screen.queryByText('Sommets')).toBeNull()
    expect(screen.getByText('Col du Truc')).not.toBeNull()
    expect(screen.getByText('Crêt du Machin')).not.toBeNull()
    // Un seul badge « sommet », sur la ligne du crêt.
    expect(screen.getAllByText('sommet')).toHaveLength(1)
    expect(screen.getAllByRole('table')).toHaveLength(1)
  })

  it('shows all rows unfolded when there are 10 or fewer', () => {
    const summaries = Array.from({ length: 10 }, (_, i) =>
      mkSummary({ id: `col-${String(i)}`, name: `Col ${String(i)}` })
    )
    render(<ColsWidget summaries={summaries} />)
    expect(screen.getAllByRole('row')).toHaveLength(11) // 10 data rows + header
    expect(screen.queryByText(/Afficher les/)).toBeNull()
  })

  it('hides rows past 10 until the toggle is expanded', () => {
    const summaries = Array.from({ length: 13 }, (_, i) =>
      mkSummary({ id: `col-${String(i)}`, name: `Col ${String(i)}` })
    )
    render(<ColsWidget summaries={summaries} />)
    expect(screen.getByText('Col 0')).not.toBeNull()
    expect(screen.getByText('Col 9')).not.toBeNull()
    // Extra rows are absent from the DOM until the user expands the list.
    expect(screen.queryByText('Col 12')).toBeNull()

    const toggle = screen.getByRole('button', { name: /Afficher les 3 autres/ })
    fireEvent.click(toggle)

    expect(screen.getByText('Col 12')).not.toBeNull()
    expect(screen.getByRole('button', { name: /Réduire/ })).not.toBeNull()
    expect(screen.queryByText(/Afficher les/)).toBeNull()
  })
})
