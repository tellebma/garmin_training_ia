// @vitest-environment jsdom
// tests/unit/components/activity-row.test.tsx
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { ActivityRow } from '@/app/(app)/_components/activity-row'
import type { ActivityRowDto } from '@/lib/dashboard/types'

const base: ActivityRowDto = {
  id: 'a1',
  garmin_activity_id: 1,
  start_time: '2026-06-20T07:00:00Z',
  sport: 'bike',
  duration_s: 3600,
  distance_m: 30000,
  elevation_gain_m: 400,
  tss: 80,
  hr_avg: 140,
}

afterEach(() => {
  cleanup()
})

describe('ActivityRow route thumbnail', () => {
  it('shows a route thumbnail when route_polyline has points', () => {
    const { container } = render(
      <ActivityRow
        activity={{
          ...base,
          route_polyline: [
            [4.0, 45.0],
            [5.0, 46.0],
          ],
        }}
      />
    )
    // The decorative thumbnail SVG is identified by its 100x100 viewBox
    // (the Lucide sport icon uses a 24x24 viewBox).
    expect(container.querySelector('svg[viewBox="0 0 100 100"]')).not.toBeNull()
  })

  it('renders no thumbnail when route_polyline is the empty sentinel', () => {
    const { container } = render(<ActivityRow activity={{ ...base, route_polyline: [] }} />)
    expect(container.querySelector('svg[viewBox="0 0 100 100"]')).toBeNull()
  })

  it('always renders the sport icon when route_polyline is the empty-array sentinel', () => {
    const { container } = render(<ActivityRow activity={{ ...base, route_polyline: [] }} />)
    expect(container.querySelector('[aria-label]')).not.toBeNull()
    expect(container.querySelector('svg[viewBox="0 0 100 100"]')).toBeNull()
  })

  it('always renders the sport icon when route_polyline is absent', () => {
    const { container } = render(<ActivityRow activity={{ ...base }} />)
    expect(container.querySelector('[aria-label]')).not.toBeNull()
  })

  it('shows the elevation gain on the row', () => {
    render(<ActivityRow activity={{ ...base, elevation_gain_m: 1238 }} />)
    expect(screen.getByText('1238 m')).toBeTruthy()
  })

  it('hides the elevation gain when the activity is flat or has none', () => {
    const { rerender } = render(<ActivityRow activity={{ ...base, elevation_gain_m: 0 }} />)
    expect(screen.queryByTitle('Dénivelé positif')).toBeNull()
    rerender(<ActivityRow activity={{ ...base, elevation_gain_m: null }} />)
    expect(screen.queryByTitle('Dénivelé positif')).toBeNull()
  })
})
