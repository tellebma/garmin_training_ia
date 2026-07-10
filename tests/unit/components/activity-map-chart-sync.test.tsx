// @vitest-environment jsdom
// tests/unit/components/activity-map-chart-sync.test.tsx
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ActivitySample } from '@/lib/coach/activity-analysis'
import type { Sport } from '@/lib/dashboard/types'

vi.mock('@/app/(app)/_components/maps/activity-route-map-lazy', () => ({
  ActivityRouteMapLazy: ({ hoverIndex }: { hoverIndex?: number | null }) => (
    <div data-testid="map-stub" data-hover-index={hoverIndex ?? 'none'} />
  ),
}))

vi.mock('@/app/(app)/_components/charts/activity-samples-chart', () => ({
  ActivitySamplesChart: ({
    onHoverIndexChange,
  }: {
    onHoverIndexChange?: (index: number | null) => void
  }) => (
    <button type="button" data-testid="hover-trigger" onClick={() => onHoverIndexChange?.(5)} />
  ),
}))

import { ActivityMapChartSync } from '@/app/(app)/_components/charts/activity-map-chart-sync'

function sample(): ActivitySample {
  return {
    sample_index: 0,
    sample_time: null,
    elapsed_s: null,
    distance_m: null,
    elevation_m: null,
    heart_rate_bpm: null,
    power_w: null,
    cadence_rpm: null,
    speed_m_s: null,
    latitude: 45.1,
    longitude: 4.1,
  }
}

const sport: Sport = 'run'

describe('ActivityMapChartSync', () => {
  afterEach(cleanup)

  it('renders the map card only when showMap is true', () => {
    render(<ActivityMapChartSync samples={[sample()]} sport={sport} showMap={false} />)
    expect(screen.queryByTestId('map-stub')).toBeNull()
    expect(screen.getByTestId('hover-trigger')).toBeTruthy()
  })

  it('forwards the hovered chart index to the map', () => {
    render(<ActivityMapChartSync samples={[sample()]} sport={sport} showMap />)
    expect(screen.getByTestId('map-stub').dataset.hoverIndex).toBe('none')

    fireEvent.click(screen.getByTestId('hover-trigger'))
    expect(screen.getByTestId('map-stub').dataset.hoverIndex).toBe('5')
  })
})
