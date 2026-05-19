import { describe, expect, it } from 'vitest'
import { isSafeNext } from '@/lib/auth/safe-next'

describe('isSafeNext (C1 anti-open-redirect)', () => {
  it('allows whitelisted /auth/set-password', () => {
    expect(isSafeNext('/auth/set-password')).toBe('/auth/set-password')
  })
  it('allows whitelisted /auth/reset-password', () => {
    expect(isSafeNext('/auth/reset-password')).toBe('/auth/reset-password')
  })
  it('allows whitelisted /today', () => {
    expect(isSafeNext('/today')).toBe('/today')
  })
  it('falls back to /today on null', () => {
    expect(isSafeNext(null)).toBe('/today')
  })
  it('falls back to /today on external URL (open redirect attempt)', () => {
    expect(isSafeNext('https://evil.com')).toBe('/today')
  })
  it('falls back to /today on path traversal attempt', () => {
    expect(isSafeNext('//evil.com')).toBe('/today')
  })
  it('falls back to /today on unknown internal path', () => {
    expect(isSafeNext('/random')).toBe('/today')
  })
})
