// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from '@/app/(app)/_components/skeletons/loading-region'

afterEach(() => {
  cleanup()
})

describe('Skeleton', () => {
  it('renders a decorative animated block that respects reduced motion', () => {
    render(<Skeleton className="h-8 w-24" data-testid="sk" />)
    const el = screen.getByTestId('sk')
    expect(el.getAttribute('aria-hidden')).toBe('true')
    expect(el.className).toContain('animate-pulse')
    expect(el.className).toContain('motion-reduce:animate-none')
    expect(el.className).toContain('h-8')
    expect(el.className).toContain('w-24')
  })
})

describe('LoadingRegion', () => {
  it('exposes an accessible status region with a label', () => {
    render(
      <LoadingRegion label="Chargement du profil">
        <Skeleton className="h-4 w-10" />
      </LoadingRegion>
    )
    const region = screen.getByRole('status')
    expect(region.getAttribute('aria-label')).toBe('Chargement du profil')
    expect(region.getAttribute('aria-busy')).toBe('true')
  })
})
