import { describe, expect, it } from 'vitest'
import { polylineToSvgPath } from '@/lib/maps/route-thumbnail'

describe('polylineToSvgPath', () => {
  it('projects a polyline into a normalized viewBox path (lat flipped on Y)', () => {
    const result = polylineToSvgPath(
      [
        [4.0, 45.0],
        [5.0, 46.0],
      ],
      100
    )
    expect(result).not.toBeNull()
    expect(result?.viewBox).toBe('0 0 100 100')
    // lng 4→5 maps x 0→100 ; lat 45 (min) is bottom → y=100, lat 46 (max) → y=0
    expect(result?.d).toBe('M0,100 L100,0')
  })

  it('returns null for fewer than 2 valid points', () => {
    expect(polylineToSvgPath([[4.0, 45.0]])).toBeNull()
    expect(polylineToSvgPath([])).toBeNull()
    expect(polylineToSvgPath(null)).toBeNull()
    expect(polylineToSvgPath('nope')).toBeNull()
  })

  it('returns null for a degenerate bbox (all points identical)', () => {
    expect(
      polylineToSvgPath([
        [4.0, 45.0],
        [4.0, 45.0],
      ])
    ).toBeNull()
  })

  it('preserves aspect ratio by centering the smaller axis', () => {
    // Wide-but-flat track: lng spans 0..10, lat spans 0..0.0001 → x uses full width,
    // y collapses near the vertical center (50).
    const result = polylineToSvgPath(
      [
        [0, 0],
        [10, 0.0001],
      ],
      100
    )
    expect(result?.d.startsWith('M0,')).toBe(true)
    expect(result?.d).toContain('L100,')
  })
})
