import { describe, expect, it } from 'vitest'
import { isLngLat } from '@/lib/maps/geo'

describe('isLngLat', () => {
  it('returns true for a valid [lng, lat] pair', () => {
    expect(isLngLat([4.0, 45.0])).toBe(true)
  })

  it('returns true for an array longer than 2 elements', () => {
    expect(isLngLat([4.0, 45.0, 100])).toBe(true)
  })

  it('returns false for null', () => {
    expect(isLngLat(null)).toBe(false)
  })

  it('returns false for an empty array', () => {
    expect(isLngLat([])).toBe(false)
  })

  it('returns false for a single-element array', () => {
    expect(isLngLat([4.0])).toBe(false)
  })

  it('returns false when either coordinate is not a number', () => {
    expect(isLngLat(['x', 45.0])).toBe(false)
    expect(isLngLat([4.0, 'y'])).toBe(false)
  })

  it('returns false when either coordinate is non-finite', () => {
    expect(isLngLat([Infinity, 45.0])).toBe(false)
    expect(isLngLat([4.0, NaN])).toBe(false)
  })

  it('returns false for a non-array value', () => {
    expect(isLngLat('4.0,45.0')).toBe(false)
    expect(isLngLat(42)).toBe(false)
  })
})
