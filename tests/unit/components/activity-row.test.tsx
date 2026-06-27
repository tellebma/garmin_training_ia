// @vitest-environment jsdom
// tests/unit/components/activity-row.test.tsx
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
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
    expect(container.querySelector('svg path')).not.toBeNull()
  })

  it('renders no thumbnail when route_polyline is the empty sentinel', () => {
    const { container } = render(<ActivityRow activity={{ ...base, route_polyline: [] }} />)
    expect(container.querySelector('svg path')).toBeNull()
  })
})
