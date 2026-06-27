import { describe, expect, it } from 'vitest'
import { parseRoutePolyline, routeToSvgPath } from '@/lib/maps/route-polyline'

describe('parseRoutePolyline', () => {
  it('parses a valid lng/lat array', () => {
    expect(
      parseRoutePolyline([
        [4.1, 45.1],
        [4.2, 45.2],
      ])
    ).toEqual([
      [4.1, 45.1],
      [4.2, 45.2],
    ])
  })

  it('drops malformed pairs and returns null below two points', () => {
    expect(parseRoutePolyline([[4.1, 45.1], [4.2], ['a', 'b']])).toBeNull()
    expect(parseRoutePolyline(null)).toBeNull()
    expect(parseRoutePolyline('nope')).toBeNull()
    expect(parseRoutePolyline([[4.1, 45.1]])).toBeNull()
  })

  it('rejects out-of-range coordinates', () => {
    expect(
      parseRoutePolyline([
        [200, 45.1],
        [4.2, 45.2],
      ])
    ).toBeNull()
  })
})

describe('routeToSvgPath', () => {
  const opts = { width: 64, height: 40, padding: 2 }

  it('returns a path starting with M and one L per extra point', () => {
    const d = routeToSvgPath(
      [
        [4.0, 45.0],
        [4.1, 45.1],
        [4.2, 45.0],
      ],
      opts
    )
    expect(d).not.toBeNull()
    expect(d?.startsWith('M')).toBe(true)
    expect((d?.match(/L/g) ?? []).length).toBe(2)
  })

  it('keeps every coordinate inside the padded box', () => {
    const d = routeToSvgPath(
      [
        [4.0, 45.0],
        [4.5, 45.4],
      ],
      opts
    )
    const nums = (d ?? '').match(/-?\d+(\.\d+)?/g)?.map(Number) ?? []
    const xs = nums.filter((_, i) => i % 2 === 0)
    const ys = nums.filter((_, i) => i % 2 === 1)
    expect(Math.min(...xs)).toBeGreaterThanOrEqual(opts.padding - 0.001)
    expect(Math.max(...xs)).toBeLessThanOrEqual(opts.width - opts.padding + 0.001)
    expect(Math.min(...ys)).toBeGreaterThanOrEqual(opts.padding - 0.001)
    expect(Math.max(...ys)).toBeLessThanOrEqual(opts.height - opts.padding + 0.001)
  })

  it('returns null for fewer than two points', () => {
    expect(routeToSvgPath([[4.0, 45.0]], opts)).toBeNull()
  })
})
