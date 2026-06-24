// @vitest-environment jsdom
import { render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

const addSource = vi.fn()
const addLayer = vi.fn()
const fitBounds = vi.fn()
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
      this.remove = vi.fn()
    }),
  },
}))

import { ActivityRouteMap } from '@/app/(app)/_components/maps/activity-route-map'
import type { ActivitySample } from '@/lib/coach/activity-analysis'

function sample(latitude: number | null, longitude: number | null): ActivitySample {
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
    latitude,
    longitude,
  }
}

describe('ActivityRouteMap', () => {
  it('adds the route source once the map loads', () => {
    render(<ActivityRouteMap samples={[sample(45.1, 4.1), sample(45.2, 4.2)]} />)
    expect(addSource).toHaveBeenCalledWith('route', expect.anything())
    expect(addLayer).toHaveBeenCalled()
    expect(fitBounds).toHaveBeenCalled()
  })
})
