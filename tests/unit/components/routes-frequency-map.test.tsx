// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => {
  const addSource = vi.fn()
  const addLayer = vi.fn()
  const fitBounds = vi.fn()
  const remove = vi.fn()
  const popupRemove = vi.fn()
  const handlers = new Map<string, (event: unknown) => void>()
  const on = vi.fn((event: string, second: unknown, third?: unknown) => {
    const cb = (typeof second === 'function' ? second : third) as (event: unknown) => void
    const key = typeof second === 'string' ? `${event}:${second}` : event
    handlers.set(key, cb)
    if (event === 'load') cb(undefined)
  })
  const canvas = { style: { cursor: '' } }
  const MapConstructor = vi.fn(function (this: Record<string, unknown>) {
    this.on = on
    this.addSource = addSource
    this.addLayer = addLayer
    this.fitBounds = fitBounds
    this.getCanvas = () => canvas
    this.remove = remove
  })
  const setLngLat = vi.fn()
  const setText = vi.fn()
  const addTo = vi.fn()
  const PopupConstructor = vi.fn(function (this: Record<string, unknown>) {
    this.setLngLat = setLngLat
    this.setText = setText
    this.addTo = addTo
    this.remove = popupRemove
  })
  return {
    addSource,
    addLayer,
    fitBounds,
    remove,
    popupRemove,
    on,
    handlers,
    canvas,
    MapConstructor,
    PopupConstructor,
    setLngLat,
    setText,
    addTo,
  }
})

vi.mock('maplibre-gl', () => ({
  default: { Map: mocks.MapConstructor, Popup: mocks.PopupConstructor },
}))

import { RoutesFrequencyMap } from '@/app/(app)/_components/maps/routes-frequency-map'

/** Two activities sharing a road, plus one activity on a road further north. */
const SHARED: [number, number][] = [
  [4.0, 45.5],
  [4.02, 45.5],
  [4.04, 45.5],
]
const ELSEWHERE: [number, number][] = [
  [4.0, 45.56],
  [4.02, 45.56],
]

beforeEach(() => {
  cleanup()
  mocks.setLngLat.mockReturnThis()
  mocks.setText.mockReturnThis()
  mocks.addTo.mockReturnThis()
  for (const mock of [
    mocks.addSource,
    mocks.addLayer,
    mocks.fitBounds,
    mocks.remove,
    mocks.popupRemove,
    mocks.MapConstructor,
    mocks.PopupConstructor,
    mocks.setLngLat,
    mocks.setText,
    mocks.addTo,
  ]) {
    mock.mockClear()
  }
  mocks.handlers.clear()
  mocks.canvas.style.cursor = ''
})

describe('RoutesFrequencyMap', () => {
  it('renders a frequency-weighted line layer and fits the route bounds', () => {
    render(<RoutesFrequencyMap polylines={[SHARED, SHARED, ELSEWHERE]} />)

    expect(mocks.addSource).toHaveBeenCalledWith('routes', expect.anything())
    const layer = mocks.addLayer.mock.calls[0]?.[0] as {
      type: string
      layout: Record<string, unknown>
      paint: Record<string, unknown>
    }
    expect(layer.type).toBe('line')
    expect(layer.layout['line-sort-key']).toEqual(['get', 'passages'])
    // Colour and width are both driven by the passages property, so the
    // encoding never relies on colour alone.
    expect(JSON.stringify(layer.paint['line-color'])).toContain('passages')
    expect(JSON.stringify(layer.paint['line-width'])).toContain('zoom')
    expect(mocks.fitBounds).toHaveBeenCalled()
  })

  it('exposes a legend and a text alternative naming the busiest road', () => {
    render(<RoutesFrequencyMap polylines={[SHARED, SHARED, ELSEWHERE]} />)

    expect(screen.getByText('Passages')).toBeDefined()
    expect(screen.getByText(/2 passages sur la route la plus empruntée/)).toBeDefined()
    // One legend entry per frequency class, plus the "Passages" caption.
    expect(screen.getAllByRole('listitem').length).toBeGreaterThanOrEqual(3)
  })

  it('shows an empty state and creates no map when no route has GPS points', () => {
    render(<RoutesFrequencyMap polylines={[[], null]} />)
    expect(mocks.MapConstructor).not.toHaveBeenCalled()
    expect(screen.getByText(/Pas encore assez de tracés GPS/)).toBeDefined()
  })

  it('opens a popup with the passage count on hover and clears it on leave', () => {
    render(<RoutesFrequencyMap polylines={[SHARED, SHARED]} />)

    mocks.handlers.get('mousemove:routes-frequency')?.({
      lngLat: { lng: 4, lat: 45.5 },
      features: [{ properties: { passages: 2 } }],
    })
    expect(mocks.setText).toHaveBeenCalledWith('2 passages')
    expect(mocks.canvas.style.cursor).toBe('pointer')

    mocks.handlers.get('mouseleave:routes-frequency')?.(undefined)
    expect(mocks.canvas.style.cursor).toBe('')
    expect(mocks.popupRemove).toHaveBeenCalled()
  })

  it('ignores a hover event that carries no feature', () => {
    render(<RoutesFrequencyMap polylines={[SHARED]} />)
    mocks.handlers.get('mousemove:routes-frequency')?.({ lngLat: { lng: 4, lat: 45.5 } })
    expect(mocks.setText).not.toHaveBeenCalled()
  })

  it('singularises the popup label for a single passage', () => {
    render(<RoutesFrequencyMap polylines={[SHARED]} />)
    mocks.handlers.get('mousemove:routes-frequency')?.({
      lngLat: { lng: 4, lat: 45.5 },
      features: [{ properties: { passages: 1 } }],
    })
    expect(mocks.setText).toHaveBeenCalledWith('1 passage')
  })

  it('removes the map and the popup when the component unmounts', () => {
    const { unmount } = render(<RoutesFrequencyMap polylines={[SHARED]} />)
    expect(mocks.remove).not.toHaveBeenCalled()
    unmount()
    expect(mocks.remove).toHaveBeenCalledTimes(1)
    expect(mocks.popupRemove).toHaveBeenCalled()
  })
})
