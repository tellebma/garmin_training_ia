// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ComponentType } from 'react'
import type { ActivitySample } from '@/lib/coach/activity-analysis'

// next/dynamic would normally code-split + skip SSR; for the unit test we
// resolve it to a synchronous stub that records the props it receives.
vi.mock('next/dynamic', () => ({
  default: (): ComponentType<{
    samples: ActivitySample[]
    height?: number
    hoverIndex?: number | null
  }> =>
    function MapStub({ samples, height, hoverIndex }) {
      return (
        <div
          data-testid="map-stub"
          data-count={samples.length}
          data-height={height ?? 'auto'}
          data-hover-index={hoverIndex ?? 'none'}
        />
      )
    },
}))

import { ActivityRouteMapLazy } from '@/app/(app)/_components/maps/activity-route-map-lazy'

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

describe('ActivityRouteMapLazy', () => {
  afterEach(cleanup)

  it('forwards samples to the dynamically loaded map', () => {
    render(<ActivityRouteMapLazy samples={[sample(), sample()]} />)
    const stub = screen.getByTestId('map-stub')
    expect(stub.dataset.count).toBe('2')
    expect(stub.dataset.height).toBe('auto')
  })

  it('forwards an explicit height when provided', () => {
    render(<ActivityRouteMapLazy samples={[sample()]} height={240} />)
    expect(screen.getByTestId('map-stub').dataset.height).toBe('240')
  })

  it('forwards hoverIndex when provided', () => {
    render(<ActivityRouteMapLazy samples={[sample()]} hoverIndex={0} />)
    expect(screen.getByTestId('map-stub').dataset.hoverIndex).toBe('0')
  })

  it('omits hoverIndex when not provided', () => {
    render(<ActivityRouteMapLazy samples={[sample()]} />)
    expect(screen.getByTestId('map-stub').dataset.hoverIndex).toBe('none')
  })
})
