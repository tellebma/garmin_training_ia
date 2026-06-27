// @vitest-environment jsdom
import { fireEvent, render } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const removeMock = vi.fn()
const addSource = vi.fn()
const addLayer = vi.fn()
const fitBounds = vi.fn()
const isStyleLoaded = vi.fn(() => true)
const getLayer = vi.fn((_id: string) => ({ id: 'route-line' }))
const setPaintProperty = vi.fn()
const on = vi.fn((event: string, cb: () => void) => {
  if (event === 'load') cb()
})

vi.mock('maplibre-gl', () => ({
  default: {
    Map: vi.fn(function (this: Record<string, unknown>) {
      this.on = on
      this.addSource = addSource
      this.addLayer = addLayer
      this.fitBounds = fitBounds
      this.isStyleLoaded = isStyleLoaded
      this.getLayer = getLayer
      this.setPaintProperty = setPaintProperty
      this.remove = removeMock
    }),
  },
}))

import { ActivityRouteMap } from '@/app/(app)/_components/maps/activity-route-map'
import type { ActivitySample } from '@/lib/coach/activity-analysis'

function sample(
  latitude: number | null,
  longitude: number | null,
  heart_rate_bpm: number | null = null,
  speed_m_s: number | null = null,
  elevation_m: number | null = null
): ActivitySample {
  return {
    sample_index: 0,
    sample_time: null,
    elapsed_s: null,
    distance_m: null,
    elevation_m,
    heart_rate_bpm,
    power_w: null,
    cadence_rpm: null,
    speed_m_s,
    latitude,
    longitude,
  }
}

describe('ActivityRouteMap', () => {
  beforeEach(() => {
    removeMock.mockClear()
    addSource.mockClear()
    addLayer.mockClear()
    fitBounds.mockClear()
    isStyleLoaded.mockClear()
    isStyleLoaded.mockReturnValue(true)
    getLayer.mockClear()
    getLayer.mockImplementation((_id: string) => ({ id: 'route-line' }))
    setPaintProperty.mockClear()
  })

  it('adds the route source once the map loads', () => {
    render(<ActivityRouteMap samples={[sample(45.1, 4.1), sample(45.2, 4.2)]} />)
    expect(addSource).toHaveBeenCalledWith('route', expect.anything())
    expect(addLayer).toHaveBeenCalled()
    expect(fitBounds).toHaveBeenCalled()
    expect(setPaintProperty).toHaveBeenCalledWith('route-line', 'line-gradient', expect.anything())
  })

  it('does not call addSource when all GPS samples are null', () => {
    render(<ActivityRouteMap samples={[sample(null, null), sample(null, null)]} />)
    expect(addSource).not.toHaveBeenCalled()
    expect(addLayer).not.toHaveBeenCalled()
  })

  it('calls map.remove() when the component unmounts (cleanup)', () => {
    const { unmount } = render(
      <ActivityRouteMap samples={[sample(45.1, 4.1), sample(45.2, 4.2)]} />
    )
    expect(removeMock).not.toHaveBeenCalled()
    unmount()
    expect(removeMock).toHaveBeenCalledTimes(1)
  })

  it('calls setPaintProperty when the user clicks a metric toggle button', () => {
    // Provide samples with GPS + HR + speed + elevation on 2+ points so that
    // availableMetrics() returns all three metrics and the toggle buttons render.
    const samples = [sample(45.1, 4.1, 140, 3.5, 200), sample(45.2, 4.2, 155, 4.0, 210)]
    const { getByText } = render(<ActivityRouteMap samples={samples} />)

    setPaintProperty.mockClear()

    // Click the "Vitesse" (speed) toggle button.
    fireEvent.click(getByText('Vitesse'))

    expect(setPaintProperty).toHaveBeenCalledWith('route-line', 'line-gradient', expect.anything())
  })
})
