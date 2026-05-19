import { describe, it, expect } from 'vitest'
import { cn } from '@/lib/utils'

describe('cn (className merge helper)', () => {
  it('joins multiple classes', () => {
    expect(cn('a', 'b', 'c')).toBe('a b c')
  })

  it('drops falsy values', () => {
    expect(cn('a', null, undefined, false, 'b')).toBe('a b')
  })

  it('handles conditional object syntax', () => {
    expect(cn('a', { b: true, c: false })).toBe('a b')
  })

  it('handles arrays of classes', () => {
    expect(cn(['a', 'b'], 'c')).toBe('a b c')
  })

  it('merges conflicting Tailwind classes (last wins)', () => {
    expect(cn('p-2', 'p-4')).toBe('p-4')
    expect(cn('text-red-500', 'text-blue-500')).toBe('text-blue-500')
  })

  it('returns empty string when called with no args', () => {
    expect(cn()).toBe('')
  })
})
