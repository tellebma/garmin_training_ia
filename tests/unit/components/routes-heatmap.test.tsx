// @vitest-environment jsdom
import { render } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => {
  const addSource = vi.fn()
  const addLayer = vi.fn()
  const fitBounds = vi.fn()
  const extend = vi.fn()
  const isEmpty = vi.fn(() => false)
  const on = vi.fn((event: string, cb: () => void) => {
    if (event === 'load') cb()
  })
  const MapConstructor = vi.fn(function (this: Record<string, unknown>) {
    this.on = on
    this.addSource = addSource
    this.addLayer = addLayer
    this.fitBounds = fitBounds
    this.remove = vi.fn()
  })
  return { addSource, addLayer, fitBounds, extend, isEmpty, on, MapConstructor }
})

vi.mock('maplibre-gl', () => ({
  default: {
    Map: mocks.MapConstructor,
    LngLatBounds: vi.fn(function (this: Record<string, unknown>) {
      this.extend = mocks.extend
      this.isEmpty = mocks.isEmpty
    }),
  },
}))

import { RoutesHeatmap } from '@/app/(app)/_components/maps/routes-heatmap'

describe('RoutesHeatmap', () => {
  beforeEach(() => {
    mocks.addSource.mockClear()
    mocks.addLayer.mockClear()
    mocks.fitBounds.mockClear()
    mocks.extend.mockClear()
    mocks.isEmpty.mockClear()
    mocks.isEmpty.mockReturnValue(false)
    mocks.MapConstructor.mockClear()
  })

  it('adds routes source, heatmap layer and fits bounds when polylines have GPS points', () => {
    render(
      <RoutesHeatmap
        polylines={[
          [
            [4.0, 45.0],
            [4.1, 45.1],
          ],
          [[5.0, 46.0]],
        ]}
      />
    )
    expect(mocks.addSource).toHaveBeenCalledWith('routes', expect.anything())
    expect(mocks.addLayer).toHaveBeenCalledWith(expect.objectContaining({ type: 'heatmap' }))
    expect(mocks.fitBounds).toHaveBeenCalled()
  })

  it('does not create a map instance when polylines produce no GPS points', () => {
    render(<RoutesHeatmap polylines={[[], null]} />)
    expect(mocks.MapConstructor).not.toHaveBeenCalled()
  })

  it('calls map.remove() when the component unmounts (cleanup)', () => {
    // Use polylines with real points so a map instance is created.
    const { unmount } = render(
      <RoutesHeatmap
        polylines={[
          [
            [4.0, 45.0],
            [4.1, 45.1],
          ],
        ]}
      />
    )
    // Grab the remove mock from the last constructed Map instance.
    const instance = mocks.MapConstructor.mock.instances[0] as { remove: ReturnType<typeof vi.fn> }
    expect(instance.remove).not.toHaveBeenCalled()
    unmount()
    expect(instance.remove).toHaveBeenCalledTimes(1)
  })
})
