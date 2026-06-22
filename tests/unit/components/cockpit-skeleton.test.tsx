// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { CockpitSkeleton } from '@/app/(app)/_components/skeletons/cockpit-skeleton'

afterEach(() => {
  cleanup()
})

describe('CockpitSkeleton', () => {
  it('renders an accessible loading region for the cockpit', () => {
    render(<CockpitSkeleton />)
    const region = screen.getByRole('status')
    expect(region.getAttribute('aria-label')).toContain('cockpit')
  })
})
